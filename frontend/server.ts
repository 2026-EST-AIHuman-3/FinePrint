import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";

const app = express();
const PORT = Number(process.env.PORT || 3000);

// React 화면 상태 확인용. RAG/Agent API는 VITE_FINEPRINT_API_URL의 Python 서버가 담당한다.
app.get("/api/health", (_req, res) => {
  res.json({ status: "ok", service: "fineprint-ui" });
});

async function start() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`FinePrint UI running on http://localhost:${PORT}`);
  });
}

start().catch((error) => {
  console.error("Failed to start FinePrint UI:", error);
  process.exitCode = 1;
});
