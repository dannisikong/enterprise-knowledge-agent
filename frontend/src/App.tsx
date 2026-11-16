import { useEffect, useState } from "react";
import { Bot, FileText, Search, ShieldCheck, Sparkles } from "lucide-react";

type Health = { status: string; service: string };

export default function App() {
  const [health, setHealth] = useState<"checking" | "ok" | "error">("checking");

  useEffect(() => {
    fetch("/api/health")
      .then((response) => {
        if (!response.ok) throw new Error("API unavailable");
        return response.json() as Promise<Health>;
      })
      .then(() => setHealth("ok"))
      .catch(() => setHealth("error"));
  }, []);

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><Bot size={21} /></span><span>KnowFlow</span></div>
        <div className="workspace-label">工作空间</div>
        <button className="nav-item active"><Sparkles size={17} /> 智能问答</button>
        <button className="nav-item"><FileText size={17} /> 知识库</button>
        <div className="sidebar-bottom">
          <div className="status-dot" />
          <span>API {health === "ok" ? "运行正常" : health === "error" ? "连接失败" : "检查中"}</span>
        </div>
      </aside>

      <section className="main-panel">
        <header className="topbar">
          <div><span className="eyebrow">ENTERPRISE KNOWLEDGE</span><h1>企业知识助手</h1></div>
          <div className="secure"><ShieldCheck size={16} /> 企业知识安全空间</div>
        </header>

        <section className="welcome">
          <div className="welcome-icon"><Sparkles size={22} /></div>
          <p className="eyebrow">YOUR KNOWLEDGE, CONNECTED</p>
          <h2>你好，今天有什么可以帮你？</h2>
          <p className="subtitle">基于企业内部知识，快速查找资料、理解制度并获得有依据的回答。</p>
          <div className="search-box"><Search size={19} /><span>例如：公司的差旅报销标准是什么？</span><kbd>Enter</kbd></div>
          <div className="hint">当前为项目初始界面，知识检索与问答能力将在后续里程碑接入。</div>
        </section>

        <section className="capabilities">
          <article><FileText size={19} /><h3>知识库管理</h3><p>集中管理企业文档与知识来源</p></article>
          <article><Search size={19} /><h3>精准检索</h3><p>从相关资料中定位可信信息</p></article>
          <article><ShieldCheck size={19} /><h3>答案可溯源</h3><p>回答附带来源，便于核验</p></article>
        </section>
      </section>
    </main>
  );
}
