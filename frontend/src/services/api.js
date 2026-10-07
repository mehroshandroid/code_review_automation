import axios from "axios";

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000/api";
const API_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, "");

axios.defaults.withCredentials = true;

axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export async function createReview(
  androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode, platform,
  devopsRepoUrl, devopsPat, devopsBranch, projectId, clauseChecklistOverrides
) {
  const formData = new FormData();
  if (androidZip) formData.append("androidZip", androidZip);
  if (excelTemplate) formData.append("excelTemplate", excelTemplate);
  if (llmProvider) formData.append("llmProvider", llmProvider);
  if (ollamaModel) formData.append("ollamaModel", ollamaModel);
  if (compileCheckMode) formData.append("compileCheckMode", compileCheckMode);
  if (platform) formData.append("platform", platform);
  if (devopsRepoUrl) formData.append("devopsRepoUrl", devopsRepoUrl);
  if (devopsPat) formData.append("devopsPat", devopsPat);
  if (devopsBranch) formData.append("devopsBranch", devopsBranch);
  if (projectId) formData.append("projectId", projectId);
  if (clauseChecklistOverrides && Object.keys(clauseChecklistOverrides).length > 0) {
    formData.append("clauseChecklistOverrides", JSON.stringify(clauseChecklistOverrides));
  }
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
}

export async function getClausePreview({ platform, file }) {
  const formData = new FormData();
  formData.append("platform", platform);
  if (file) formData.append("file", file);
  const response = await axios.post(`${API_BASE_URL}/reviews/clause-preview`, formData);
  return response.data.categories;
}

export async function getProgress(reviewId) {
  const response = await axios.get(`${API_BASE_URL}/reviews/${reviewId}/progress`);
  return response.data;
}

export async function getOllamaModels() {
  const response = await axios.get(`${API_BASE_URL}/ollama/models`);
  return response.data.models;
}

export function getDownloadUrl(downloadPath) {
  return `${API_ORIGIN}${downloadPath}`;
}

export function getMicrosoftLoginUrl() {
  return `${API_BASE_URL}/auth/microsoft/login`;
}

export async function createProject(name) {
  const response = await axios.post(`${API_BASE_URL}/projects`, { name });
  return response.data;
}

export async function getProjects() {
  const response = await axios.get(`${API_BASE_URL}/projects`);
  return response.data.projects;
}

export async function updateProject(projectId, name) {
  const response = await axios.patch(`${API_BASE_URL}/projects/${projectId}`, { name });
  return response.data;
}

export async function getProjectReviews(projectId) {
  const response = await axios.get(`${API_BASE_URL}/projects/${projectId}/reviews`);
  return response.data.reviews;
}

export async function getReview(reviewId) {
  const response = await axios.get(`${API_BASE_URL}/reviews/${reviewId}`);
  return response.data;
}

export async function updateReview(reviewId, { categoryScores, status } = {}) {
  const body = {};
  if (categoryScores !== undefined) body.category_scores = categoryScores;
  if (status !== undefined) body.status = status;
  const response = await axios.patch(`${API_BASE_URL}/reviews/${reviewId}`, body);
  return response.data;
}

export async function getReviewers() {
  const response = await axios.get(`${API_BASE_URL}/reviewers`);
  return response.data.reviewers;
}

export async function setReviewReviewer(reviewId, reviewerId) {
  const response = await axios.patch(`${API_BASE_URL}/reviews/${reviewId}/reviewer`, { reviewer_id: reviewerId });
  return response.data;
}

export async function deleteReview(reviewId) {
  await axios.delete(`${API_BASE_URL}/reviews/${reviewId}`);
}

export async function getLlmProviderSettings() {
  const response = await axios.get(`${API_BASE_URL}/settings/llm-provider`);
  return response.data;
}

export async function updateLlmProviderSettings(defaultLlmProvider, defaultOllamaModel) {
  const response = await axios.put(`${API_BASE_URL}/settings/llm-provider`, {
    default_llm_provider: defaultLlmProvider,
    default_ollama_model: defaultOllamaModel,
  });
  return response.data;
}

export async function getClauseChecklists() {
  const response = await axios.get(`${API_BASE_URL}/settings/clause-checklists`);
  return response.data.checklists;
}

export async function upsertClauseChecklist(platform, subId, checklistText) {
  const response = await axios.put(
    `${API_BASE_URL}/settings/clause-checklists/${platform}/${subId}`,
    { checklist_text: checklistText }
  );
  return response.data;
}

export async function deleteClauseChecklist(platform, subId) {
  await axios.delete(`${API_BASE_URL}/settings/clause-checklists/${platform}/${subId}`);
}

export async function getSampleTemplates() {
  const response = await axios.get(`${API_BASE_URL}/settings/sample-templates`);
  return response.data.templates;
}

export async function uploadSampleTemplate(platform, file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await axios.post(`${API_BASE_URL}/settings/sample-templates/${platform}`, formData);
  return response.data;
}

export async function deleteSampleTemplate(platform) {
  await axios.delete(`${API_BASE_URL}/settings/sample-templates/${platform}`);
}

export async function previewSampleTemplate(platform) {
  const response = await axios.get(`${API_BASE_URL}/settings/sample-templates/${platform}/preview`);
  return response.data.categories;
}

export async function sendChatMessage(message, history = []) {
  const response = await axios.post(`${API_BASE_URL}/chat`, {
    message,
    history: history.map((entry) => ({ role: entry.role, content: entry.content })),
  });
  return response.data;
}

export async function getReviews({ year, platform, projectId } = {}) {
  const params = { year };
  if (platform) params.platform = platform;
  if (projectId) params.project_id = projectId;
  const response = await axios.get(`${API_BASE_URL}/reviews`, { params });
  return response.data.reviews;
}

export async function getReviewYears() {
  const response = await axios.get(`${API_BASE_URL}/reviews/years`);
  return response.data.years;
}

export async function uploadCompletedReview({ projectId, platform, file }) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("projectId", projectId);
  formData.append("platform", platform);
  const response = await axios.post(`${API_BASE_URL}/reviews/upload`, formData);
  return response.data;
}

export async function login(email, password) {
  const response = await axios.post(`${API_BASE_URL}/auth/login`, { email, password });
  return response.data;
}

export async function logout() {
  await axios.post(`${API_BASE_URL}/auth/logout`);
}

export async function getCurrentUser() {
  const response = await axios.get(`${API_BASE_URL}/auth/me`);
  return response.data;
}

export async function listUsers() {
  const response = await axios.get(`${API_BASE_URL}/users`);
  return response.data.users;
}

export async function createUser(email, password, role, name) {
  const response = await axios.post(`${API_BASE_URL}/users`, { email, password, role, name: name || null });
  return response.data;
}

export async function updateUser(userId, { role, isActive, password, name } = {}) {
  const body = {};
  if (role !== undefined) body.role = role;
  if (isActive !== undefined) body.is_active = isActive;
  if (password !== undefined) body.password = password;
  if (name !== undefined) body.name = name;
  const response = await axios.patch(`${API_BASE_URL}/users/${userId}`, body);
  return response.data;
}

export async function deleteUser(userId) {
  await axios.delete(`${API_BASE_URL}/users/${userId}`);
}

export async function getMyReviews() {
  const response = await axios.get(`${API_BASE_URL}/my/reviews`);
  return response.data.reviews;
}

export async function getProjectManagers() {
  const response = await axios.get(`${API_BASE_URL}/project-managers`);
  return response.data.managers;
}

export async function setProjectManagers(projectId, userIds) {
  const response = await axios.put(`${API_BASE_URL}/projects/${projectId}/managers`, { user_ids: userIds });
  return response.data;
}

export async function deleteProject(projectId) {
  await axios.delete(`${API_BASE_URL}/projects/${projectId}`);
}
