import axios from "axios";
import { createReview, getProgress, getDownloadUrl, getOllamaModels } from "./api";

jest.mock("axios");

describe("createReview", () => {
  it("posts multipart form data with both files and returns the response body", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    const result = await createReview(zip, xlsx);

    expect(result).toEqual({ review_id: "abc-123", status: "processing" });
    expect(axios.post).toHaveBeenCalledTimes(1);
    const [url, formData] = axios.post.mock.calls[0];
    expect(url).toContain("/reviews");
    expect(formData.get("androidZip")).toBe(zip);
    expect(formData.get("excelTemplate")).toBe(xlsx);
  });

  it("includes llmProvider and ollamaModel fields when provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx, "ollama", "qwen2.5-coder:7b");

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("llmProvider")).toBe("ollama");
    expect(formData.get("ollamaModel")).toBe("qwen2.5-coder:7b");
  });

  it("omits llmProvider and ollamaModel fields when not provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx);

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("llmProvider")).toBeNull();
    expect(formData.get("ollamaModel")).toBeNull();
  });

  it("includes compileCheckMode field when provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx, "azure", null, "static");

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("compileCheckMode")).toBe("static");
  });
});

describe("getProgress", () => {
  it("fetches progress for a review id and returns the response body", async () => {
    const progressBody = {
      status: "processing", phase: "scoring", progress: 60, message: "Scoring",
      stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    };
    axios.get.mockResolvedValue({ data: progressBody });

    const result = await getProgress("abc-123");

    expect(result).toEqual(progressBody);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/reviews/abc-123/progress"));
  });
});

describe("getOllamaModels", () => {
  it("fetches installed Ollama models and returns the list", async () => {
    axios.get.mockResolvedValue({ data: { models: ["mistral:latest", "qwen2.5-coder:7b"] } });

    const result = await getOllamaModels();

    expect(result).toEqual(["mistral:latest", "qwen2.5-coder:7b"]);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/ollama/models"));
  });
});

describe("getDownloadUrl", () => {
  it("combines the API origin with the backend's returned download path without doubling /api", () => {
    const url = getDownloadUrl("/api/reviews/abc-123/download");
    expect(url).toBe("http://localhost:8000/api/reviews/abc-123/download");
  });
});
