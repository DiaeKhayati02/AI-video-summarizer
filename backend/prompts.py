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
    template="""You are answering questions about a YouTube video using its transcript as your \
only source of truth. If the answer is not in the transcript, say you don't know based on the \
video.

Transcript:
{transcript}

Conversation so far:
{chat_history}

Question: {question}
Answer:""",
)
