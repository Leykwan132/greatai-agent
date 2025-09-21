import json
import logging
from dotenv import load_dotenv
from livekit.agents import (
    NOT_GIVEN,
    Agent,
    AgentFalseInterruptionEvent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
)
from livekit import rtc  # Import rtc for room events
from typing import List, Dict, Any, Optional
from datetime import datetime
from livekit.agents.llm import function_tool
from livekit.plugins import noise_cancellation, silero, aws
from livekit.plugins.turn_detector.multilingual import MultilingualModel
import requests
import base64
from email.mime.text import MIMEText
import re
import os

load_dotenv(".env.local")


access_token = None
URL = os.getenv("URL")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are Alexis, a voice assistant that helps users manage their email and calendar using this software, please .
            Begin with a greeting with the user, keep it a 1 liner strictly.
            You have access to tools for handling emails and calendar events; use only these tools to assist the user. Always be helpful, friendly, and professional. If a request is unclear or not specific enough, ask the user to clarify what they want to do and for which email or calendar event.
            Stick strictly to the language used in your first message throughout the conversation, even if the user switches languages. Politely inform the user to end and restart the call to choose another language if needed.
            Your responses will be read aloud by text-to-speech. Format your output as it should be spoken: for example, say 'team at elevenlabs dot I O' instead of 'team at elevenlabs dot I O.' Do not use bullet points, bold, headers, or code samples in your responses. Instead of long lists, summarize and ask the user which part they are interested in. Ignore spelling mistakes rather than correcting them.
            Keep your answers short—just a couple of sentences—and let the user guide you for more details if needed.

            IMPORTANT EMAIL WORKFLOW:
            - When users want to view emails, use viewAllEmailWithLabels to get a list of emails with their details
            - Each email in the response contains an 'email_id' field (e.g., "199697489918bc26")
            - When replying to emails, use the 'email_id' value from the viewAllEmailWithLabels response as the email_id parameter in replyToEmail
            - Do NOT make up email_id values - always use the email_id from the actual email data returned by viewAllEmailWithLabels

            IMPORTANT CALENDAR ATTENDEE FORMAT:
            - When creating or updating calendar events, attendees must be provided as plain email addresses only
            - Correct format: "feliciayin197@gmail.com"
            - Incorrect format: "Shuang Yin <feliciayin197@gmail.com>"
            - The API expects attendees as a list of email strings, which will be automatically formatted as {"email": "address"} for the Google Calendar API

            Allowed tools:
            - viewAllEmailWithLabels: Use when the user wants to hear emails filtered by importance or label.
            - replyToEmail: Use when the user wants to reply to an email. The email_id parameter should come from the 'email_id' field in the response from viewAllEmailWithLabels.
            - getTodayCalendarEvents: Use when the user wants to know their events for today.
            - createCalendarEvent: Use when the user wants to create a new event.
            - editCalendarEvent: Use when the user wants to update an event.
            Use only tools listed above. For routine read-only tasks, call automatically. For operations that change or remove information, require user confirmation before proceeding.
Guardrails:
- Only address email and calendar management topics. If asked about unrelated subjects, state you can only help with email and calendar.
- Use only one tool per interaction: each new tool action overrides the previous.
- Keep responses conversational with minimal technical detail. Guide users when more clarification is needed or to the right action.""",
        )

    @function_tool
    async def viewAllEmailWithLabels(self, label: str) -> List[Dict[str, Any]]:
        """
        View emails filtered by label  using Gmail API.

        Args:
            label: Filter emails by specific label (e.g., 'work', 'personal', 'urgent') - required

        Example:
            label: "Work"

        Returns:
            {
            "emails": [
                {
                "email_id": "199697489918bc26",
                "snippet": "Hi im testing",
                "subject": "Testing only",
                "from": "leykwan132@gmail.com"
                },
                {
                "email_id": "199689eaf471d381",
                "snippet": "Hi Kwan Can you send set up a meeting later for client? Thanks",
                "subject": "Set up meeting",
                "from": "Shuang Yin <feliciayin197@gmail.com>"
                }
            ],
            "count": 2
            }

        """

        try:
            # First, get the user's profile to identify the Gmail user ID
            url = f"{URL}/emails?label={label}"
            headers = {"Authorization": f"Bearer {access_token}"}

            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            return data

        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch emails via Gmail API: {e}")
            return {
                "status": "error",
                "message": f"Failed to fetch emails: {str(e)}",
                "emails": [],
            }
        except Exception as e:
            logging.error(f"Unexpected error fetching emails: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
                "emails": [],
            }

    @function_tool
    async def replyToEmail(
        self,
        email_id: str,
        to: str,
        body: str,
    ) -> Dict[str, Any]:
        """
        Reply to a specific email using Gmail API.

        Args:
            email_id: Unique identifier of the email to reply to. This should come from the 'email_id' field in the response from viewAllEmailWithLabels function.
            to: Recipient of the reply
            body: Reply message content

        Example:
            email_id: "199697489918bc26" (from viewAllEmailWithLabels response)
            to: "recipient@example.com"
            body: "Hello, this is a reply."

        CURL equivalent:
            curl -X POST {URL}/emails/reply \\
              -H "Content-Type: application/json" \\
              -H "Authorization: Bearer {access_token}" \\
              -d '{{
                "message_id": "{email_id}",
                "to": "{to}",
                "body": "{body}"
              }}'

        Returns:
            Confirmation of sent reply with details
        """

        try:
            url = f"{URL}/emails/reply"

            response = requests.post(
                url,
                json={
                    "message_id": email_id,
                    "to": to,
                    "body": body,
                },
            )
            response.raise_for_status()
            data = response.json()

            return data
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send reply via Gmail API: {e}")
            return {
                "status": "error",
                "message": f"Failed to send reply: {str(e)}",
            }
        except Exception as e:
            logging.error(f"Unexpected error sending reply: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @function_tool
    async def getTodayCalendarEvents(self) -> list[dict[str, Any]]:
        """
        Get today's calendar events using Google Calendar API.

        Returns:
            List of calendar events for the specified day
        """

        try:
            # First, get the user's profile to identify the Gmail user ID
            url = f"{URL}/calendar/events"

            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            return data

        except requests.exceptions.RequestException as e:
            logging.error(
                f"Failed to fetch calendar events via Google Calendar API: {e}"
            )
            return {
                "status": "error",
                "message": f"Failed to fetch calendar events: {str(e)}",
                "events": [],
            }
        except Exception as e:
            logging.error(f"Unexpected error fetching calendar events: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
                "events": [],
            }

    @function_tool
    async def editCalendarEvent(
        self,
        event_id: str,
        start_time: str,
        end_time: str,
        summary: str,
    ) -> dict:
        """
        Edit an existing calendar event using Google Calendar API.

        Args:
            event_id: Unique identifier of the event to edit
            start_time: New start time in ISO format
            end_time: New end time in ISO format
            summary: current event summary

        Example:
            event_id: "1234567890"
            start_time: "2025-09-22T09:00:00+08:00",
            end_time: "2025-09-22T10:00:00+08:00",
            summary: "Test Event",

        CURL equivalent:
            curl -X PUT {URL}calendar/events/{event_id} \\
              -H "Content-Type: application/json" \\
              -H "Authorization: Bearer {access_token}" \\
              -d '{{
                "summary": "{summary}",
                "start": {{
                  "dateTime": "{start_time}",
                  "timeZone": "Asia/Kuala_Lumpur"
                }},
                "end": {{
                  "dateTime": "{end_time}",
                  "timeZone": "Asia/Kuala_Lumpur"
                }}
              }}'

        Returns:
            Confirmation of updated event
        """
        # Check if access token is available

        try:
            url = f"{URL}calendar/events/{event_id}"

            response = requests.put(
                url,
                json={
                    "summary": summary,
                    "start": {
                        "dateTime": start_time,
                        "timeZone": "Asia/Kuala_Lumpur",
                    },
                    "end": {
                        "dateTime": end_time,
                        "timeZone": "Asia/Kuala_Lumpur",
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

            return data

        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to edit calendar event via Google Calendar API: {e}")
            return {
                "status": "error",
                "message": f"Failed to edit calendar event: {str(e)}",
            }
        except Exception as e:
            logging.error(f"Unexpected error editing calendar event: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }

    @function_tool
    async def createCalendarEvent(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        location: str,
        description: str,
        attendees: List[str],
    ) -> dict:
        """
        Create a new calendar event using Google Calendar API.

        Args:
            summary: New event summary
            start_time: calendar start time in ISO format
            end_time: calendar end time in ISO format
            location: New location
            description: New description
            attendees: New attendees (list of email addresses only - NO display names)

        IMPORTANT: Attendees must be plain email addresses only:
        - ✅ Correct: ["feliciayin197@gmail.com", "user@example.com"]
        - ❌ Incorrect: ["Shuang Yin <feliciayin197@gmail.com>", "User Name <user@example.com>"]

        Example:
            summary: "Test Event",
            start_time: "2025-09-22T09:00:00+08:00",
            end_time: "2025-09-22T10:00:00+08:00",
            location: "Meeting Room 1",
            description: "Test meeting description",
            attendees: [
            "feliciayin197@gmail.com"
            ]

        Returns:
            Confirmation of created event
        """
        # Check if access token is available

        try:
            url = f"{URL}/calendar/events"

            response = requests.post(
                url,
                json={
                    "summary": summary,
                    "start": {
                        "dateTime": start_time,
                        "timeZone": "Asia/Kuala_Lumpur",
                    },
                    "end": {
                        "dateTime": end_time,
                        "timeZone": "Asia/Kuala_Lumpur",
                    },
                    "location": location,
                    "description": description,
                    "attendees": [{"email": attendee} for attendee in attendees],
                },
            )
            response.raise_for_status()
            data = response.json()

            return data
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to edit calendar event via Google Calendar API: {e}")
            return {
                "status": "error",
                "message": f"Failed to edit calendar event: {str(e)}",
            }
        except Exception as e:
            logging.error(f"Unexpected error editing calendar event: {e}")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}",
            }


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using OpenAI, Cartesia, Deepgram, and the LiveKit turn detector
    session = AgentSession(
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all providers at https://docs.livekit.io/agents/integrations/llm/
        llm=aws.realtime.RealtimeModel(voice="matthew"),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # sometimes background noise could interrupt the agent session, these are considered false positive interruptions
    # when it's detected, you may resume the agent's speech
    @session.on("agent_false_interruption")
    def _on_agent_false_interruption(ev: AgentFalseInterruptionEvent):
        logging.info("false positive interruption, resuming")
        session.generate_reply(instructions=ev.extra_instructions or NOT_GIVEN)

    # Metrics collection, to measure pipeline performance
    # For more information, see https://docs.livekit.io/agents/build/metrics/
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    # Log usage summary on shutdown
    async def log_usage():
        summary = usage_collector.get_summary()
        logging.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/integrations/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/integrations/avatar/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # LiveKit Cloud enhanced noise cancellation
            # - If self-hosting, omit this parameter
            # - For telephony applications, use `BVCTelephony` for best results
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
