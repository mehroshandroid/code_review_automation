import axios from "axios";

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000/api";
const API_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, "");

export async function createReview(
  androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode, platform,
  devopsRepoUrl, devopsPat, devopsBranch, projectId
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
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
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
