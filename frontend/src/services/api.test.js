import axios from "axios";
import {
  createReview, getProgress, getDownloadUrl, getOllamaModels, createProject, updateProject, getProjects, getProjectReviews, getReview,
  getLlmProviderSettings, updateLlmProviderSettings, getClauseChecklists, upsertClauseChecklist, deleteClauseChecklist,
  getSampleTemplates, uploadSampleTemplate, deleteSampleTemplate,
} from "./api";

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

  it("includes platform field when provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx, "azure", null, "compiler", "Android");

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("platform")).toBe("Android");
  });

  it("includes devops fields when provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(
      null, xlsx, "azure", null, "compiler", "Android",
      "https://dev.azure.com/myorg/MyProject/_git/my-repo", "fake-pat", "release/1.0"
    );

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("androidZip")).toBeNull();
    expect(formData.get("devopsRepoUrl")).toBe("https://dev.azure.com/myorg/MyProject/_git/my-repo");
    expect(formData.get("devopsPat")).toBe("fake-pat");
    expect(formData.get("devopsBranch")).toBe("release/1.0");
  });

  it("omits devops fields when not provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx);

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("devopsRepoUrl")).toBeNull();
    expect(formData.get("devopsPat")).toBeNull();
    expect(formData.get("devopsBranch")).toBeNull();
  });

  it("includes projectId field when provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx, "azure", null, "compiler", "Android", null, null, null, "proj-1");

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("projectId")).toBe("proj-1");
  });

  it("omits projectId field when not provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    await createReview(zip, xlsx);

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("projectId")).toBeNull();
  });

  it("omits excelTemplate field when not provided", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });

    await createReview(zip, null);

    const [, formData] = axios.post.mock.calls[0];
    expect(formData.get("excelTemplate")).toBeNull();
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

describe("createProject", () => {
  it("posts the given name and returns the created project", async () => {
    const project = { id: "p1", name: "Payments Service", created_at: "2026-08-07T00:00:00Z" };
    axios.post.mockResolvedValue({ data: project });

    const result = await createProject("Payments Service");

    expect(result).toEqual(project);
    expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/projects"), { name: "Payments Service" });
  });
});

describe("getProjects", () => {
  it("fetches all projects and returns the list", async () => {
    const projects = [{ id: "p1", name: "Payments Service", created_at: "2026-08-07T00:00:00Z" }];
    axios.get.mockResolvedValue({ data: { projects } });

    const result = await getProjects();

    expect(result).toEqual(projects);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/projects"));
  });
});

describe("updateProject", () => {
  it("patches the given name and returns the updated project", async () => {
    const project = { id: "p1", name: "Renamed Project", created_at: "2026-08-07T00:00:00Z" };
    axios.patch.mockResolvedValue({ data: project });

    const result = await updateProject("p1", "Renamed Project");

    expect(result).toEqual(project);
    expect(axios.patch).toHaveBeenCalledWith(expect.stringContaining("/projects/p1"), { name: "Renamed Project" });
  });
});

describe("getProjectReviews", () => {
  it("fetches reviews for a project id and returns the list", async () => {
    const reviews = [{ id: "r1", platform: "Android", status: "pending_approval", total_score_pct: 90 }];
    axios.get.mockResolvedValue({ data: { reviews } });

    const result = await getProjectReviews("p1");

    expect(result).toEqual(reviews);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/projects/p1/reviews"));
  });
});

describe("getReview", () => {
  it("fetches a single review by id and returns the response body", async () => {
    const review = { id: "r1", platform: "Android", status: "pending_approval", category_scores: [] };
    axios.get.mockResolvedValue({ data: review });

    const result = await getReview("r1");

    expect(result).toEqual(review);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/reviews/r1"));
  });
});

describe("getDownloadUrl", () => {
  it("combines the API origin with the backend's returned download path without doubling /api", () => {
    const url = getDownloadUrl("/api/reviews/abc-123/download");
    expect(url).toBe("http://localhost:8000/api/reviews/abc-123/download");
  });
});

describe("getLlmProviderSettings", () => {
  it("fetches the org-wide LLM provider default", async () => {
    const settings = { default_llm_provider: "ollama", default_ollama_model: "qwen2.5-coder:7b" };
    axios.get.mockResolvedValue({ data: settings });

    const result = await getLlmProviderSettings();

    expect(result).toEqual(settings);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/settings/llm-provider"));
  });
});

describe("updateLlmProviderSettings", () => {
  it("puts the new default provider and model and returns the response body", async () => {
    const settings = { default_llm_provider: "azure", default_ollama_model: null };
    axios.put.mockResolvedValue({ data: settings });

    const result = await updateLlmProviderSettings("azure", null);

    expect(result).toEqual(settings);
    expect(axios.put).toHaveBeenCalledWith(
      expect.stringContaining("/settings/llm-provider"),
      { default_llm_provider: "azure", default_ollama_model: null }
    );
  });
});

describe("getClauseChecklists", () => {
  it("fetches all clause checklists and returns the list", async () => {
    const checklists = [{ platform: ".NET", sub_id: "2.4", checklist_text: "Check JWT config" }];
    axios.get.mockResolvedValue({ data: { checklists } });

    const result = await getClauseChecklists();

    expect(result).toEqual(checklists);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/settings/clause-checklists"));
  });
});

describe("upsertClauseChecklist", () => {
  it("puts the checklist text for the given platform and sub id", async () => {
    const checklist = { platform: ".NET", sub_id: "2.4", checklist_text: "Check JWT config" };
    axios.put.mockResolvedValue({ data: checklist });

    const result = await upsertClauseChecklist(".NET", "2.4", "Check JWT config");

    expect(result).toEqual(checklist);
    expect(axios.put).toHaveBeenCalledWith(
      expect.stringContaining("/settings/clause-checklists/.NET/2.4"),
      { checklist_text: "Check JWT config" }
    );
  });
});

describe("deleteClauseChecklist", () => {
  it("deletes the checklist for the given platform and sub id", async () => {
    axios.delete.mockResolvedValue({});

    await deleteClauseChecklist(".NET", "2.4");

    expect(axios.delete).toHaveBeenCalledWith(expect.stringContaining("/settings/clause-checklists/.NET/2.4"));
  });
});

describe("getSampleTemplates", () => {
  it("fetches all configured sample templates and returns the list", async () => {
    const templates = [{ platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" }];
    axios.get.mockResolvedValue({ data: { templates } });

    const result = await getSampleTemplates();

    expect(result).toEqual(templates);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/settings/sample-templates"));
  });
});

describe("uploadSampleTemplate", () => {
  it("posts the file as multipart form data for the given platform and returns the response body", async () => {
    const template = { platform: "Android", filename: "android-default.xlsx", uploaded_at: "2026-08-07T00:00:00Z" };
    axios.post.mockResolvedValue({ data: template });
    const file = new File(["xlsx content"], "android-default.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    const result = await uploadSampleTemplate("Android", file);

    expect(result).toEqual(template);
    const [url, formData] = axios.post.mock.calls[0];
    expect(url).toContain("/settings/sample-templates/Android");
    expect(formData.get("file")).toBe(file);
  });
});

describe("deleteSampleTemplate", () => {
  it("deletes the sample template for the given platform", async () => {
    axios.delete.mockResolvedValue({});

    await deleteSampleTemplate("Android");

    expect(axios.delete).toHaveBeenCalledWith(expect.stringContaining("/settings/sample-templates/Android"));
  });
});
