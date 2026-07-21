import express from "express";
import path from "path";
import dotenv from "dotenv";
import { GoogleGenAI, Type } from "@google/genai";
import { createServer as createViteServer } from "vite";

// Load environment variables
dotenv.config();

const app = express();
const PORT = 3000;

app.use(express.json());

// Lazy-loaded Gemini Client
let aiInstance: GoogleGenAI | null = null;
function getAI() {
  if (!aiInstance) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      throw new Error("GEMINI_API_KEY environment variable is required. Please set it in the Secrets panel in AI Studio UI.");
    }
    aiInstance = new GoogleGenAI({
      apiKey,
      httpOptions: {
        headers: {
          'User-Agent': 'aistudio-build',
        }
      }
    });
  }
  return aiInstance;
}

// Health check endpoint
app.get("/api/health", (req, res) => {
  res.json({ status: "ok" });
});

// Endpoint: Register service and generate suggested questions
app.post("/api/analyze", async (req, res) => {
  try {
    const { type, query } = req.body;
    if (!query || !query.trim()) {
      return res.status(400).json({ error: "Query is required" });
    }

    const ai = getAI();

    let serviceIdentifierPrompt = "";
    if (type === "name") {
      serviceIdentifierPrompt = `The user wants to analyze the service named "${query}". Please extract/confirm the correct, professional Korean/English service name and generate exactly 3 highly relevant suggested questions users typically have regarding subscription, auto-renewal, refund, or penalty terms for this specific service.`;
    } else if (type === "url") {
      serviceIdentifierPrompt = `The user provided this URL: "${query}". Please extract/identify the service name from this URL, and generate exactly 3 highly relevant suggested questions users typically have regarding subscription, auto-renewal, refund, or privacy terms for this service.`;
    } else {
      serviceIdentifierPrompt = `The user provided this raw terms document text:\n\n${query.substring(0, 1000)}\n\nPlease extract/determine a suitable short service/product name from this text, and generate exactly 3 highly relevant suggested questions based on potential risks found in this document.`;
    }

    const systemInstruction = `You are an expert AI Legal Assistant that helps subscribers register a service for terms Q&A.
Your job is to:
1. Extract or clean the exact, professional name of the subscription service (e.g., "Netflix", "YouTube Premium", "Adobe Creative Cloud", "Spotify"). If the input is raw text, find the company or product name.
2. Generate exactly 3 highly tailored, practical Korean questions that a normal user would ask about refunds, automatic renewals, privacy policy, or hidden fees for this specific service. (e.g. '결제된 지 7일 이내인데 환불 가능한가요?', '가족 멤버십을 공유하면 정지될 수 있나요?'). Ensure the questions are written in natural, helpful Korean.`;

    const responseSchema = {
      type: Type.OBJECT,
      properties: {
        serviceName: { type: Type.STRING, description: "The clean, professional name of the identified service (e.g. Netflix, YouTube Premium)." },
        suggestedQuestions: {
          type: Type.ARRAY,
          items: { type: Type.STRING },
          description: "An array of exactly 3 practical, service-specific Korean questions about terms, refund, renewal, or privacy."
        }
      },
      required: ["serviceName", "suggestedQuestions"]
    };

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: serviceIdentifierPrompt,
      config: {
        systemInstruction,
        responseMimeType: "application/json",
        responseSchema,
      },
    });

    const resultText = response.text;
    if (!resultText) {
      throw new Error("Empty response received from Gemini");
    }

    const parsedResult = JSON.parse(resultText);
    res.json(parsedResult);
  } catch (error: any) {
    console.error("Service Registration Error:", error);
    res.status(500).json({ error: error.message || "Internal Server Error" });
  }
});

// Endpoint: AI Agent RAG-based Subscription Q&A
app.post("/api/question", async (req, res) => {
  try {
    const { serviceName, type, originalQuery, question } = req.body;
    if (!question || !question.trim()) {
      return res.status(400).json({ error: "Question is required" });
    }

    const ai = getAI();

    // Prepare context based on whether they uploaded a doc, url, or entered name
    let contextStr = `Service Name: "${serviceName || "Unknown"}"\n`;
    if (type === "document" && originalQuery) {
      contextStr += `Original Terms Document snippet provided by user:\n${originalQuery.substring(0, 3000)}\n`;
    } else if (type === "url" && originalQuery) {
      contextStr += `Terms URL provided: "${originalQuery}"\n`;
    }

    const userPrompt = `
Context of service:
${contextStr}

User Question:
"${question}"

Please analyze this question using the exact terms of "${serviceName}" and South Korean Consumer Protection agency guidelines (한국 공정거래위원회 및 한국소비자원 기준).
If the service or the specific clause is not in the text, leverage your extensive knowledge about ${serviceName}'s actual, current global and Korean refund, cancellation, renewal, and fee policies to give an accurate, precise, and highly reliable response.
`;

    const systemInstruction = `You are FinePrint, an expert and deeply empathetic AI legal assistant specialized in subscription terms analysis.
Your goal is to answer the user's specific question about their subscription issue, cross-referencing the service's actual policies and Korean consumer protection guidelines.

You MUST follow the provided JSON schema.
- 'category': Must be one of: refund, renewal, privacy, fees, other
- 'answer': A highly clear, polite, and reassuring Korean explanation of what happens in this situation. Be practical and empathetic.
- 'evidence': A concise Korean summary/paraphrase of the specific legal clause that applies to this situation.
- 'originalText': The direct, raw English or Korean terms quote that supports this finding. (e.g. "Members can request a refund within 7 days...")
- 'todo': An array of exactly 2 to 3 actionable, step-by-step checklist items in Korean the user can do right now to defend their rights.
- 'materials': An array of 1 to 3 physical or digital items/documents the user needs to prepare (e.g., '결제 카드 영수증 캡처본', '구글 플레이 주문 번호').
- 'draft': (Optional) A polite, professionally-written support email or dispute draft in Korean that the user can copy-paste and send to customer support to request a refund, dispute, or cancellation. It MUST use clean, natural Korean with standard line breaks for paragraph separation. DO NOT write the literal character letters '\\n' or '\\\\n' or any programming escape codes as visible text in the string; make it fully-formed human natural language with real line breaks. Include placeholders like [이름], [아이디] where appropriate. If not relevant, leave as an empty string.`;

    const responseSchema = {
      type: Type.OBJECT,
      properties: {
        category: { type: Type.STRING, description: "One of: refund, renewal, privacy, fees, other" },
        answer: { type: Type.STRING, description: "Detailed, practical answer and advice in empathetic Korean." },
        evidence: { type: Type.STRING, description: "Summary/paraphrase of the specific applicable term or legal basis in Korean." },
        originalText: { type: Type.STRING, description: "Raw legal text quote representing the policy." },
        todo: {
          type: Type.ARRAY,
          items: { type: Type.STRING },
          description: "2 to 3 direct actions the user can take."
        },
        materials: {
          type: Type.ARRAY,
          items: { type: Type.STRING },
          description: "1 to 3 items/screenshots the user needs to prepare."
        },
        draft: { type: Type.STRING, description: "Official Korean customer support query draft template with placeholders. Keep empty if not applicable." }
      },
      required: ["category", "answer", "evidence", "originalText", "todo", "materials", "draft"]
    };

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: userPrompt,
      config: {
        systemInstruction,
        responseMimeType: "application/json",
        responseSchema,
      },
    });

    const resultText = response.text;
    if (!resultText) {
      throw new Error("Empty response received from Gemini");
    }

    const parsedResult = JSON.parse(resultText);

    // Clean up literal newline text representations for a fully natural user experience
    const sanitizeText = (str: any): string => {
      if (typeof str !== "string") return str;
      return str
        .replace(/\\n/g, "\n")
        .replace(/\\r/g, "\r")
        .replace(/\r\n/g, "\n");
    };

    if (parsedResult.draft) parsedResult.draft = sanitizeText(parsedResult.draft);
    if (parsedResult.answer) parsedResult.answer = sanitizeText(parsedResult.answer);
    if (parsedResult.evidence) parsedResult.evidence = sanitizeText(parsedResult.evidence);
    if (parsedResult.originalText) parsedResult.originalText = sanitizeText(parsedResult.originalText);
    if (Array.isArray(parsedResult.todo)) {
      parsedResult.todo = parsedResult.todo.map(sanitizeText);
    }
    if (Array.isArray(parsedResult.materials)) {
      parsedResult.materials = parsedResult.materials.map(sanitizeText);
    }

    res.json(parsedResult);
  } catch (error: any) {
    console.error("Q&A Processing Error:", error);
    res.status(500).json({ error: error.message || "Internal Server Error" });
  }
});

// Start server
async function start() {
  if (process.env.NODE_ENV !== "production") {
    // Development Mode with Vite Middleware
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
    console.log("Vite development middleware mounted");
  } else {
    // Production Mode serving static files
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on port ${PORT}`);
  });
}

start().catch((err) => {
  console.error("Failed to start server:", err);
});
