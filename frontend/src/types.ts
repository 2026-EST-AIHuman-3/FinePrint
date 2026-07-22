export type QACategory = 'refund' | 'renewal' | 'privacy' | 'fees' | 'other';

export interface QAItem {
  id: string;
  question: string;
  category: QACategory;
  answer: string;       // AI's detailed explanation and guidance
  evidence: string;     // Extracted legal terms evidence summary
  originalText: string; // Raw terms quote
  todo: {
    id: string;
    text: string;
    checked: boolean;
  }[];
  materials?: string[]; // Required preparation materials
  draft?: string;       // Customer support draft message
  timestamp: string;
  problemType?: string;
  termsEvidence?: string[];
  sourceReferences?: string[];
  checkItems?: string[];
  nextActions?: string[];
  followUpQuestions?: string[];
}

export interface KnowledgeBaseStatus {
  service_name: string;
  service_documents_ready: boolean;
  reference_documents_ready: boolean;
  policy_status: {
    terms: boolean;
    privacy: boolean;
  };
  missing_policy_types: Array<'terms' | 'privacy'>;
  requires_policy_input: boolean;
}

export interface HistoryItem {
  id: string;
  serviceName: string;
  type: 'name' | 'url' | 'document';
  query: string;        // Initial service identifier or document
  date: string;
  queries: QAItem[];    // The sub-list of user questions asked under this service
  selectedQAId?: string; // Currently focused QA item ID
  suggestedQuestions?: string[]; // Recommended initial questions for this service
  knowledgeBaseStatus?: KnowledgeBaseStatus;
}

export function formatServiceName(name: string): string {
  const trimmed = name.trim();
  const lower = trimmed.toLowerCase();
  
  // If it already has both Korean and English (e.g. contains parentheses), return as is
  if (/\(.*\)/.test(trimmed)) {
    return trimmed;
  }

  // Pre-defined mappings for bilingual service names
  const mappings = [
    { key: "netflix", display: "넷플릭스 (Netflix)" },
    { key: "넷플릭스", display: "넷플릭스 (Netflix)" },
    { key: "tving", display: "티빙 (TVING)" },
    { key: "티빙", display: "티빙 (TVING)" },
    { key: "youtube premium", display: "유튜브 프리미엄 (YouTube Premium)" },
    { key: "유튜브 프리미엄", display: "유튜브 프리미엄 (YouTube Premium)" },
    { key: "youtube", display: "유튜브 (YouTube)" },
    { key: "유튜브", display: "유튜브 (YouTube)" },
    { key: "spotify", display: "스포티파이 (Spotify)" },
    { key: "스포티파이", display: "스포티파이 (Spotify)" },
    { key: "notion", display: "노션 (Notion)" },
    { key: "노션", display: "노션 (Notion)" },
    { key: "zoom", display: "줌 (Zoom)" },
    { key: "줌", display: "줌 (Zoom)" },
    { key: "adobe creative cloud", display: "어도비 크리에이티브 클라우드 (Adobe Creative Cloud)" },
    { key: "adobe", display: "어도비 크리에이티브 클라우드 (Adobe Creative Cloud)" },
    { key: "어도비", display: "어도비 크리에이티브 클라우드 (Adobe Creative Cloud)" },
    { key: "coupang wow", display: "쿠팡 와우 (Coupang Wow)" },
    { key: "coupang", display: "쿠팡 (Coupang)" },
    { key: "쿠팡 와우", display: "쿠팡 와우 (Coupang Wow)" },
    { key: "쿠팡", display: "쿠팡 (Coupang)" },
    { key: "naver plus", display: "네이버플러스 멤버십 (Naver Plus)" },
    { key: "네이버플러스", display: "네이버플러스 멤버십 (Naver Plus)" },
    { key: "class101", display: "클래스101 (CLASS101)" },
    { key: "클래스101", display: "클래스101 (CLASS101)" },
    { key: "millie", display: "밀리의 서재 (Millie)" },
    { key: "밀리의 서재", display: "밀리의 서재 (Millie)" },
    { key: "genie music", display: "지니뮤직 (Genie Music)" },
    { key: "genie", display: "지니뮤직 (Genie Music)" },
    { key: "지니뮤직", display: "지니뮤직 (Genie Music)" },
    { key: "melon", display: "멜론 (Melon)" },
    { key: "멜론", display: "멜론 (Melon)" },
    { key: "disney+", display: "디즈니플러스 (Disney+)" },
    { key: "disney plus", display: "디즈니플러스 (Disney+)" },
    { key: "디즈니플러스", display: "디즈니플러스 (Disney+)" },
    { key: "디즈니", display: "디즈니플러스 (Disney+)" }
  ];

  for (const m of mappings) {
    if (lower === m.key || lower.includes(m.key)) {
      return m.display;
    }
  }

  return trimmed;
}
