const state = {
  file: null,
  fileUrl: "",
  jobId: "",
  pollTimer: null,
  videoUrl: "",
  activeArtifact: "",
};

const $ = (id) => document.getElementById(id);

const elements = {
  healthBadge: $("healthBadge"),
  refreshBtn: $("refreshBtn"),
  messageList: $("messageList"),
  composer: $("composer"),
  imageInput: $("imageInput"),
  dropZone: $("dropZone"),
  pickImageBtn: $("pickImageBtn"),
  filePreview: $("filePreview"),
  problemText: $("problemText"),
  visionModel: $("visionModel"),
  codeModel: $("codeModel"),
  visionBaseUrl: $("visionBaseUrl"),
  codeBaseUrl: $("codeBaseUrl"),
  visionApiKeyEnv: $("visionApiKeyEnv"),
  codeApiKeyEnv: $("codeApiKeyEnv"),
  preferVisionOverText: $("preferVisionOverText"),
  inputMode: $("inputMode"),
  quality: $("quality"),
  noRender: $("noRender"),
  submitBtn: $("submitBtn"),
  jobTitle: $("jobTitle"),
  cancelBtn: $("cancelBtn"),
  progressBar: $("progressBar"),
  stageText: $("stageText"),
  videoFrame: $("videoFrame"),
  videoPlayer: $("videoPlayer"),
  videoEmpty: $("videoEmpty"),
  cinemaBtn: $("cinemaBtn"),
  downloadLink: $("downloadLink"),
  artifactTabs: $("artifactTabs"),
  artifactView: $("artifactView"),
  logView: $("logView"),
  cinemaOverlay: $("cinemaOverlay"),
  cinemaVideo: $("cinemaVideo"),
  closeCinemaBtn: $("closeCinemaBtn"),
  watchMessages: $("watchMessages"),
  watchForm: $("watchForm"),
  watchInput: $("watchInput"),
};

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function addMessage(role, text, imageUrl) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `
    <div class="avatar">${role === "user" ? "你" : "MT"}</div>
    <div class="message-body">
      <p></p>
    </div>
  `;
  article.querySelector("p").textContent = text;
  if (imageUrl) {
    const img = document.createElement("img");
    img.src = imageUrl;
    img.alt = "题目图片预览";
    article.querySelector(".message-body").appendChild(img);
  }
  elements.messageList.appendChild(article);
  elements.messageList.scrollTop = elements.messageList.scrollHeight;
}

function addWatchMessage(role, text) {
  const article = document.createElement("article");
  article.className = `watch-message ${role}`;
  article.textContent = text;
  elements.watchMessages.appendChild(article);
  elements.watchMessages.scrollTop = elements.watchMessages.scrollHeight;
}

function setHealth(ok, text) {
  elements.healthBadge.textContent = text;
  elements.healthBadge.classList.toggle("ok", ok);
  elements.healthBadge.classList.toggle("error", !ok);
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const data = await response.json();
    setHealth(Boolean(data.ok && data.scriptExists), data.scriptExists ? "后端已连接" : "缺少后端脚本");
  } catch (error) {
    setHealth(false, "后端未连接");
  }
}

function setFile(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    addMessage("assistant", "请选择图片文件。");
    return;
  }
  state.file = file;
  if (state.fileUrl) URL.revokeObjectURL(state.fileUrl);
  state.fileUrl = URL.createObjectURL(file);
  elements.filePreview.classList.remove("hidden");
  elements.filePreview.replaceChildren();
  const img = document.createElement("img");
  img.src = state.fileUrl;
  img.alt = "已选择图片";
  const meta = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = file.name;
  const size = document.createElement("span");
  size.textContent = formatBytes(file.size);
  meta.append(name, size);
  elements.filePreview.append(img, meta);
}

function setSubmitting(isSubmitting) {
  elements.submitBtn.disabled = isSubmitting;
  elements.submitBtn.querySelector("span").textContent = isSubmitting ? "提交中" : "开始生成";
}

function resetOutputForJob(job) {
  state.jobId = job.id;
  state.activeArtifact = "";
  elements.jobTitle.textContent = `任务 ${job.id.slice(-8)}`;
  elements.cancelBtn.classList.remove("hidden");
  elements.artifactTabs.innerHTML = "";
  elements.artifactView.textContent = "等待生成文件。";
  elements.logView.textContent = "暂无日志。";
  updateProgress(job);
}

function updateProgress(job) {
  elements.progressBar.style.width = `${job.progress || 0}%`;
  elements.stageText.textContent = job.stage || job.status || "等待状态更新";
  if (job.status === "error") {
    elements.stageText.style.color = "var(--danger)";
  } else {
    elements.stageText.style.color = "";
  }
}

function renderArtifacts(job) {
  const names = job.artifacts || [];
  elements.artifactTabs.innerHTML = "";
  if (!names.length) {
    elements.artifactView.textContent = "暂无生成文件。";
    return;
  }
  names.forEach((name) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = name;
    button.className = state.activeArtifact === name ? "active" : "";
    button.addEventListener("click", () => loadArtifact(job.id, name));
    elements.artifactTabs.appendChild(button);
  });
  if (!state.activeArtifact) {
    const preferred = names.includes("solution.md") ? "solution.md" : names[0];
    loadArtifact(job.id, preferred);
  }
}

async function loadArtifact(jobId, name) {
  state.activeArtifact = name;
  [...elements.artifactTabs.children].forEach((button) => {
    button.classList.toggle("active", button.textContent === name);
  });
  elements.artifactView.textContent = "读取中...";
  try {
    const response = await fetch(`/api/jobs/${jobId}/artifact/${encodeURIComponent(name)}`, { cache: "no-store" });
    elements.artifactView.textContent = await response.text();
  } catch (error) {
    elements.artifactView.textContent = `读取失败：${error.message}`;
  }
}

function renderVideo(job) {
  if (!job.hasVideo || !job.videoUrl) return;
  const url = job.videoUrl;
  if (state.videoUrl !== url) {
    state.videoUrl = url;
    elements.videoPlayer.src = url;
    elements.videoFrame.classList.remove("empty");
    elements.videoEmpty.classList.add("hidden");
    elements.cinemaBtn.disabled = false;
    elements.downloadLink.classList.remove("disabled");
    elements.downloadLink.href = url;
  }
}

async function refreshJob() {
  if (!state.jobId) return;
  try {
    const response = await fetch(`/api/jobs/${state.jobId}`, { cache: "no-store" });
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || "状态读取失败");
    updateProgress(job);
    renderArtifacts(job);
    renderVideo(job);
    elements.logView.textContent = job.logTail || "暂无日志。";
    if (job.status === "done" || job.status === "error") {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
      elements.cancelBtn.classList.add("hidden");
      addMessage("assistant", job.status === "done" ? "视频已生成，可以打开影院模式边看边问。" : "任务失败，右侧日志里有后端输出。");
    }
  } catch (error) {
    elements.logView.textContent = `状态读取失败：${error.message}`;
  }
}

async function submitJob(event) {
  event.preventDefault();
  if (!state.file) {
    addMessage("assistant", "请先选择一张题目图片。");
    return;
  }
  setSubmitting(true);
  const form = new FormData();
  form.append("image", state.file);
  form.append("problemText", elements.problemText.value.trim());
  form.append("inputMode", elements.inputMode.value);
  form.append("quality", elements.quality.value);
  form.append("jsonMode", "json_object");
  form.append("noRender", elements.noRender.checked ? "true" : "false");
  form.append("preferVisionOverText", elements.preferVisionOverText.checked ? "true" : "false");
  if (elements.visionModel.value.trim()) form.append("visionModel", elements.visionModel.value.trim());
  if (elements.codeModel.value.trim()) form.append("model", elements.codeModel.value.trim());
  if (elements.visionBaseUrl.value.trim()) form.append("visionBaseUrl", elements.visionBaseUrl.value.trim());
  if (elements.codeBaseUrl.value.trim()) form.append("baseUrl", elements.codeBaseUrl.value.trim());
  if (elements.visionApiKeyEnv.value.trim()) form.append("visionApiKeyEnv", elements.visionApiKeyEnv.value.trim());
  if (elements.codeApiKeyEnv.value.trim()) form.append("apiKeyEnv", elements.codeApiKeyEnv.value.trim());

  const summary = elements.problemText.value.trim()
    ? "已提交图片和补充题面，开始生成视频。"
    : "已提交图片，开始生成视频。";
  addMessage("user", summary, state.fileUrl);

  try {
    const response = await fetch("/api/jobs", { method: "POST", body: form });
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || "提交失败");
    resetOutputForJob(job);
    addMessage("assistant", "任务已接入后端，正在轮询生成状态。");
    if (state.pollTimer) window.clearInterval(state.pollTimer);
    state.pollTimer = window.setInterval(refreshJob, 2500);
    await refreshJob();
  } catch (error) {
    addMessage("assistant", `提交失败：${error.message}`);
  } finally {
    setSubmitting(false);
  }
}

async function cancelJob() {
  if (!state.jobId) return;
  try {
    await fetch(`/api/jobs/${state.jobId}/cancel`, { method: "POST" });
    await refreshJob();
  } catch (error) {
    addMessage("assistant", `取消失败：${error.message}`);
  }
}

function openCinema() {
  if (!state.videoUrl) return;
  elements.cinemaOverlay.classList.add("active");
  elements.cinemaVideo.src = state.videoUrl;
  elements.cinemaVideo.currentTime = elements.videoPlayer.currentTime || 0;
  if (elements.videoPlayer.paused === false) {
    elements.videoPlayer.pause();
    elements.cinemaVideo.play().catch(() => {});
  }
  const request = elements.cinemaOverlay.requestFullscreen || elements.cinemaOverlay.webkitRequestFullscreen;
  if (request) {
    const result = request.call(elements.cinemaOverlay);
    if (result && typeof result.catch === "function") result.catch(() => {});
  }
}

function closeCinema() {
  elements.videoPlayer.currentTime = elements.cinemaVideo.currentTime || 0;
  elements.cinemaVideo.pause();
  elements.cinemaOverlay.classList.remove("active");
  if (document.fullscreenElement) {
    const result = document.exitFullscreen();
    if (result && typeof result.catch === "function") result.catch(() => {});
  }
}

async function askQuestion(event) {
  event.preventDefault();
  const message = elements.watchInput.value.trim();
  if (!message || !state.jobId) return;
  const currentTime = elements.cinemaVideo.currentTime || elements.videoPlayer.currentTime || 0;
  elements.cinemaVideo.pause();
  elements.videoPlayer.pause();
  addWatchMessage("user", message);
  elements.watchInput.value = "";
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobId: state.jobId, message, currentTime }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "问答接口失败");
    addWatchMessage("assistant", data.answer);
  } catch (error) {
    addWatchMessage("assistant", `问答接口错误：${error.message}`);
  }
}

elements.pickImageBtn.addEventListener("click", () => elements.imageInput.click());
elements.imageInput.addEventListener("change", (event) => setFile(event.target.files[0]));
elements.composer.addEventListener("submit", submitJob);
elements.refreshBtn.addEventListener("click", () => {
  checkHealth();
  refreshJob();
});
elements.cancelBtn.addEventListener("click", cancelJob);
elements.cinemaBtn.addEventListener("click", openCinema);
elements.closeCinemaBtn.addEventListener("click", closeCinema);
elements.watchForm.addEventListener("submit", askQuestion);

["dragenter", "dragover"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.remove("dragging");
  });
});

elements.dropZone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files?.[0];
  setFile(file);
});

elements.dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    elements.imageInput.click();
  }
});

document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && elements.cinemaOverlay.classList.contains("active")) {
    elements.cinemaOverlay.classList.remove("active");
  }
});

checkHealth();
