// Locally (docker-compose), the backend is same-machine on :8000. Deployed,
// frontend (Vercel) and backend (Render) live on different domains, so we
// point at the deployed backend URL instead.
const PROD_BACKEND_URL = "https://ai-video-summarizer-backend-b2l6.onrender.com";
const IS_LOCAL = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const BACKEND_URL = window.BACKEND_URL || (IS_LOCAL ? "http://localhost:8000" : PROD_BACKEND_URL);

let currentVideoId = null;

const intro = document.getElementById("intro");
const urlInput = document.getElementById("url-input");
const summariseBtn = document.getElementById("summarise-btn");
const errorBanner = document.getElementById("error-banner");
const newSummaryBtn = document.getElementById("new-summary-btn");

const workspace = document.getElementById("workspace");
const videoThumbnail = document.getElementById("video-thumbnail");
const durationBadge = document.getElementById("duration-badge");
const videoTitle = document.getElementById("video-title");
const videoChannel = document.getElementById("video-channel");
const videoDescription = document.getElementById("video-description");
const keyTakeaways = document.getElementById("key-takeaways");
const videoLink = document.getElementById("video-link");

const suggestedQuestions = document.getElementById("suggested-questions");
const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const questionInput = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");

function showError(msg) {
  errorBanner.textContent = msg;
  errorBanner.classList.remove("hidden");
}

function clearError() {
  errorBanner.classList.add("hidden");
  errorBanner.textContent = "";
}

function showLoading(button, isLoading, loadingText) {
  const label = button.querySelector(".btn-label");
  const spinner = button.querySelector(".spinner");
  if (!button.dataset.originalText) {
    button.dataset.originalText = label.textContent;
  }
  button.disabled = isLoading;
  label.textContent = isLoading ? loadingText : button.dataset.originalText;
  spinner.classList.toggle("hidden", !isLoading);
}

function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Math.round(totalSeconds || 0));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function renderSuggestedQuestions(questions) {
  suggestedQuestions.innerHTML = "";
  (questions || []).forEach((question) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "suggested-chip";
    chip.textContent = question;
    chip.addEventListener("click", () => {
      if (!currentVideoId) return;
      renderMessage(question, "user");
      suggestedQuestions.innerHTML = "";
      fetchAnswer(currentVideoId, question);
    });
    suggestedQuestions.appendChild(chip);
  });
}

function renderSummary(data) {
  videoThumbnail.src = `https://img.youtube.com/vi/${data.video_id}/hqdefault.jpg`;
  durationBadge.textContent = formatDuration(data.duration_seconds);
  videoTitle.textContent = data.title || "Untitled video";
  videoChannel.textContent = data.channel_name || "";
  videoChannel.classList.toggle("hidden", !data.channel_name);
  videoDescription.textContent = data.description;
  videoLink.href = `https://www.youtube.com/watch?v=${data.video_id}`;

  keyTakeaways.innerHTML = "";
  (data.key_takeaways || []).forEach((point) => {
    const li = document.createElement("li");
    li.textContent = point;
    keyTakeaways.appendChild(li);
  });

  renderSuggestedQuestions(data.suggested_questions);

  intro.classList.add("hidden");
  workspace.classList.remove("hidden");
  newSummaryBtn.classList.remove("hidden");
}

function renderMessage(content, role) {
  const bubble = document.createElement("div");
  bubble.classList.add("chat-bubble", role === "user" ? "chat-bubble--user" : "chat-bubble--assistant");
  bubble.textContent = content;
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function resetToIntro() {
  currentVideoId = null;
  urlInput.value = "";
  clearError();
  chatMessages.innerHTML = "";
  suggestedQuestions.innerHTML = "";
  keyTakeaways.innerHTML = "";
  questionInput.value = "";
  workspace.classList.add("hidden");
  newSummaryBtn.classList.add("hidden");
  intro.classList.remove("hidden");
  urlInput.focus();
}

async function fetchSummary(url) {
  clearError();
  showLoading(summariseBtn, true, "Summarising...");
  try {
    const res = await fetch(`${BACKEND_URL}/summarise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Failed to summarise this video.");
    }

    currentVideoId = data.video_id;
    renderSummary(data);
    chatMessages.innerHTML = "";
    await loadHistory(currentVideoId);
    if (!chatMessages.children.length) {
      renderMessage("I've read the video. Ask me anything about it.", "assistant");
    }
  } catch (err) {
    showError(err.message);
  } finally {
    showLoading(summariseBtn, false);
  }
}

async function fetchAnswer(videoId, question) {
  showLoading(sendBtn, true, "Sending...");
  try {
    const res = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: videoId, question }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Failed to get an answer.");
    }

    renderMessage(data.answer, "assistant");
  } catch (err) {
    renderMessage(`Sorry, something went wrong: ${err.message}`, "assistant");
  } finally {
    showLoading(sendBtn, false);
  }
}

async function loadHistory(videoId) {
  const res = await fetch(`${BACKEND_URL}/history/${videoId}`);
  if (!res.ok) return;
  const messages = await res.json();
  messages.forEach((m) => renderMessage(m.content, m.role));
}

summariseBtn.addEventListener("click", () => {
  const url = urlInput.value.trim();
  if (!url) {
    showError("Please paste a YouTube URL.");
    return;
  }
  fetchSummary(url);
});

urlInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    summariseBtn.click();
  }
});

newSummaryBtn.addEventListener("click", resetToIntro);

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question || !currentVideoId) return;

  renderMessage(question, "user");
  suggestedQuestions.innerHTML = "";
  questionInput.value = "";
  questionInput.style.height = "auto";
  fetchAnswer(currentVideoId, question);
});

questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

questionInput.addEventListener("input", () => {
  questionInput.style.height = "auto";
  questionInput.style.height = `${questionInput.scrollHeight}px`;
});
