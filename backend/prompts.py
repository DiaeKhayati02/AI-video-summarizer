from langchain_core.prompts import PromptTemplate

STRUCTURED_SUMMARY_PROMPT = PromptTemplate(
    input_variables=["text"],
    template="""You are analysing a YouTube video transcript. Based on the transcript below, \
produce:
- A concise 2-3 sentence description of what the video covers.
- 4-6 key takeaways as short, specific bullet points (concrete claims, numbers, steps -- not \
vague generalities).
- 3 example questions a viewer might naturally ask about this specific video, phrased naturally \
and specifically to its content (not generic questions that could apply to any video).

Transcript:
{text}""",
)

SUMMARY_MAP_PROMPT = PromptTemplate(
    input_variables=["text"],
    template="""Summarise the following section of a video transcript, capturing the key points \
and any concrete details (names, numbers, claims).

Section:
{text}

Section summary:""",
)

QA_PROMPT = PromptTemplate(
    input_variables=["transcript", "chat_history", "question"],
    template="""You're a friendly, knowledgeable assistant chatting with someone about a YouTube \
video they just watched. Use the transcript below as your primary source for what's actually *in* \
the video, but don't limit yourself to reciting it back -- bring in relevant context, background \
knowledge, or your own take when it's genuinely useful, and say so naturally (e.g. "the video \
doesn't get into this, but..."). Be warm and conversational, not clipped or robotic. Only fall \
back to saying you don't know if the question is truly unanswerable, not just because the exact \
words aren't in the transcript.

Transcript:
{transcript}

Conversation so far:
{chat_history}

Question: {question}
Answer:""",
)
