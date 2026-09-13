Coach calendar agent feature
1. Explicit voice/text commands like "add gym tomorrow at 5" now write to Google Calendar automatically.
2. Gemini only extracts intent and event fields; trusted backend validation performs the calendar write.
3. Coach recommendations can create a pending draft from the current plan and ask for approval.
4. Approval phrases like "yes" or "go ahead" confirm the pending draft into Google Calendar.
5. Every write still checks writable Google calendars, event validity, and free/busy conflicts.
6. The chat response returns calendar_event so the UI refreshes agenda and plan immediately.
7. Narration now uses coach_brief for warmer, less technical voice output.
8. Coach guidance can reference Aditya's Body Battery trajectory forecast without dumping raw data.
9. Old harness files were removed because latest dev replaced them with forecast trajectory.
