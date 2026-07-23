import type { KnowledgeBaseStatus, QACategory } from "../types";

const API_BASE = (import.meta.env.VITE_FINEPRINT_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export type DocumentType = "terms" | "privacy";
export type AnalysisType = "name" | "url" | "document";

export interface AnalyzeSubmission {
  type: AnalysisType;
  serviceName: string;
  url?: string;
  documentType?: DocumentType;
  file?: File;
}

export interface AgentAnswer {
  problemType: string;
  category: QACategory;
  simpleExplanation: string;
  termsEvidence: string[];
  sourceReferences: string[];
  checkItems: string[];
  nextActions: string[];
  requiredMaterials: string[];
  inquiryDraft: string;
  followUpQuestions: string[];
}

async function readResponse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message || body?.error || "FinePrint 서버 요청에 실패했습니다.";
    throw new Error(message);
  }
  return body as T;
}

export async function prepareService(serviceName: string): Promise<KnowledgeBaseStatus> {
  const response = await fetch(`${API_BASE}/services/prepare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ service_name: serviceName }),
  });
  return readResponse<KnowledgeBaseStatus>(response);
}

export async function ingestServiceUrl(
  serviceName: string,
  url: string,
  documentType: DocumentType,
): Promise<KnowledgeBaseStatus> {
  const response = await fetch(`${API_BASE}/services/url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      service_name: serviceName,
      url,
      document_type: documentType,
    }),
  });
  return readResponse<KnowledgeBaseStatus>(response);
}

export async function uploadServiceDocument(
  serviceName: string,
  file: File,
  documentType: DocumentType,
): Promise<KnowledgeBaseStatus> {
  const form = new FormData();
  form.append("service_name", serviceName);
  form.append("document_type", documentType);
  form.append("file", file, file.name);

  const response = await fetch(`${API_BASE}/services/document`, {
    method: "POST",
    body: form,
  });
  return readResponse<KnowledgeBaseStatus>(response);
}

function inferCategory(problemType: string): QACategory {
  if (problemType.includes("환불") || problemType.includes("청약철회")) return "refund";
  if (problemType.includes("자동") || problemType.includes("갱신")) return "renewal";
  if (problemType.includes("개인정보") || problemType.includes("프라이버시")) return "privacy";
  if (problemType.includes("결제") || problemType.includes("요금") || problemType.includes("위약금")) return "fees";
  return "other";
}

export async function askAgent(serviceName: string, question: string): Promise<AgentAnswer> {
  const response = await fetch(`${API_BASE}/questions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ service_name: serviceName, question }),
  });
  const body = await readResponse<{ answer: Record<string, unknown> }>(response);
  const answer = body.answer || {};
  const problemType = String(answer.problem_type || "약관 관련 문의");
  const outOfScopeMessage = typeof answer.message === "string" ? answer.message : "";

  return {
    problemType,
    category: inferCategory(problemType),
    simpleExplanation: outOfScopeMessage || String(answer.simple_explanation || "답변을 생성하지 못했습니다."),
    termsEvidence: Array.isArray(answer.terms_evidence) ? answer.terms_evidence.map(String) : [],
    sourceReferences: Array.isArray(answer.source_references) ? answer.source_references.map(String) : [],
    checkItems: Array.isArray(answer.check_items) ? answer.check_items.map(String) : [],
    nextActions: Array.isArray(answer.next_actions) ? answer.next_actions.map(String) : [],
    requiredMaterials: Array.isArray(answer.required_materials) ? answer.required_materials.map(String) : [],
    inquiryDraft: String(answer.inquiry_draft || ""),
    followUpQuestions: Array.isArray(answer.follow_up_questions) ? answer.follow_up_questions.map(String) : [],
  };
}

