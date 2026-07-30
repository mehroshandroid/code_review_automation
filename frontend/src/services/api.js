import axios from "axios";

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000/api";
const API_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, "");

export async function createReview(
  androidZip, excelTemplate, llmProvider, ollamaModel, compileCheckMode, platform,
  devopsRepoUrl, devopsPat, devopsBranch
) {
  const formData = new FormData();
  if (androidZip) formData.append("androidZip", androidZip);
  formData.append("excelTemplate", excelTemplate);
  if (llmProvider) formData.append("llmProvider", llmProvider);
  if (ollamaModel) formData.append("ollamaModel", ollamaModel);
  if (compileCheckMode) formData.append("compileCheckMode", compileCheckMode);
  if (platform) formData.append("platform", platform);
  if (devopsRepoUrl) formData.append("devopsRepoUrl", devopsRepoUrl);
  if (devopsPat) formData.append("devopsPat", devopsPat);
  if (devopsBranch) formData.append("devopsBranch", devopsBranch);
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
