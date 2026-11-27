import { ChangeEvent, FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import {
  Bot, FileText, ShieldCheck, Sparkles, Upload, CheckCircle2, Loader2,
  AlertCircle, Search, Send, BookOpen, Settings, Plus, Trash2, Square,
  MessageSquare, PanelLeftClose, PanelLeftOpen,
} from "lucide-react";
import { readSSEStream } from "./services/stream";
import ChatMessage from "./components/chat/ChatMessage";
import ModelSettings, { type ModelSettingsValue } from "./components/settings/ModelSettings";
import { apiFetch, ensureSession } from "./services/api";

type KnowledgeDocument = {
  id: string; filename: string; size: number; status: string;
  character_count: number; chunk_count: number; embedded_chunk_count: number;
};
type ChatSource = {
  id: number; chunk_id: string; document_id: string; filename: string;
  chunk_index: number; content: string; score?: number; rerank_score?: number;
};
type Conversation = {
  id: string; title: string; created_at: string; updated_at: string; message_count: number;
};
type ChatItem = {
  id: string; role: "user" | "assistant"; content: string;
  sources: ChatSource[]; created_at: string; streaming?: boolean;
};
type SearchResult = {
  chunk_id: string; document_id: string; filename: string;
  chunk_index: number; content: string; score: number;
  keyword_rank?: number; vector_rank?: number; rerank_score?: number;
};
type ComparisonResult = { mode: string; results: SearchResult[]; error?: string; fallback?: string; reranker?: string; rerankerError?: string };
const formatSize = (size: number) => size < 1024 * 1024 ? (size / 1024).toFixed(1) + " KB" : (size / 1024 / 1024).toFixed(1) + " MB";

export default function App() {
  const [health, setHealth] = useState<"checking" | "ok" | "error">("checking");
  const [activeSection, setActiveSection] = useState<"chat" | "documents">("chat");
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [modelSettings, setModelSettings] = useState<ModelSettingsValue>({ api_key: "", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-max" });
  const [modelTesting, setModelTesting] = useState(false);
  const [modelStatus, setModelStatus] = useState("");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [rerankEnabled, setRerankEnabled] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [comparison, setComparison] = useState<ComparisonResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [chatItems, setChatItems] = useState<ChatItem[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatStatus, setChatStatus] = useState<"idle" | "connecting" | "streaming" | "completed" | "error">("idle");
  const [chatError, setChatError] = useState("");
  const [pageMessage, setPageMessage] = useState("");
  const [pageError, setPageError] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [expandedSources, setExpandedSources] = useState<string[]>([]);
  const [highlightedSource, setHighlightedSource] = useState<string | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const activeConversationRef = useRef<string | null>(null);

  const loadDocuments = async () => {
    const response = await apiFetch("/documents");
    if (!response.ok) throw new Error("无法加载文档列表");
    setDocuments(await response.json() as KnowledgeDocument[]);
  };

  const loadConversations = async () => {
    const response = await apiFetch("/conversations");
    if (!response.ok) throw new Error("无法加载历史对话");
    const rows = await response.json() as Conversation[];
    setConversations(rows);
    return rows;
  };

  const loadMessages = async (conversationId: string) => {
    const response = await apiFetch("/conversations/" + encodeURIComponent(conversationId) + "/messages");
    if (!response.ok) throw new Error("无法加载对话消息");
    const payload = await response.json() as { messages: Array<{ id: string; role: "user" | "assistant"; content: string; sources?: ChatSource[]; created_at: string }> };
    setChatItems(payload.messages.map(item => ({ ...item, sources: item.sources || [] })));
  };

  useEffect(() => {
    let alive = true;
    ensureSession().then(async () => {
      const response = await apiFetch("/health");
      if (!response.ok) throw new Error("API unavailable");
      await Promise.all([loadDocuments(), loadConversations()]);
      if (alive) setHealth("ok");
    }).catch(() => { if (alive) { setHealth("error"); setPageError("服务连接失败，请刷新页面重试。"); } });
    return () => { alive = false; chatAbortRef.current?.abort(); };
  }, []);

  useEffect(() => { activeConversationRef.current = activeConversationId; }, [activeConversationId]);

  const createConversation = async () => {
    if (chatLoading) return;
    setChatError("");
    const response = await apiFetch("/conversations", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
    });
    if (!response.ok) throw new Error("创建新对话失败");
    const created = await response.json() as Conversation;
    setActiveConversationId(created.id);
    setChatItems([]);
    await loadConversations();
    setActiveSection("chat");
    chatInputRef.current?.focus();
  };

  const selectConversation = async (id: string) => {
    if (chatLoading || id === activeConversationId) return;
    chatAbortRef.current?.abort();
    setChatLoading(false);
    setChatError("");
    setChatStatus("idle");
    setActiveConversationId(id);
    setChatItems([]);
    try { await loadMessages(id); }
    catch (error) { setChatError(error instanceof Error ? error.message : "加载对话失败"); }
    setActiveSection("chat");
  };

  const removeConversation = async (id: string) => {
    if (!window.confirm("确定删除这段对话及其消息记录吗？")) return;
    const response = await apiFetch("/conversations/" + encodeURIComponent(id), { method: "DELETE" });
    if (!response.ok) { setChatError("删除对话失败，请重试。"); return; }
    if (activeConversationId === id) {
      chatAbortRef.current?.abort();
      setActiveConversationId(null);
      setChatItems([]);
      setChatLoading(false);
    }
    await loadConversations();
  };

  const handleSend = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    const question = chatInput.trim();
    if (!question || chatLoading) return;
    let conversationId = activeConversationId;
    try {
      if (!conversationId) {
        const response = await apiFetch("/conversations", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        if (!response.ok) throw new Error("创建对话失败");
        const created = await response.json() as Conversation;
        conversationId = created.id;
        setActiveConversationId(created.id);
      }
      const targetId = conversationId;
      setChatInput("");
      setChatError("");
      setChatStatus("connecting");
      setChatLoading(true);
      const userItem: ChatItem = { id: "local-user-" + Date.now(), role: "user", content: question, sources: [], created_at: new Date().toISOString() };
      const assistantId = "local-assistant-" + Date.now();
      const assistantItem: ChatItem = { id: assistantId, role: "assistant", content: "", sources: [], created_at: new Date().toISOString(), streaming: true };
      setChatItems(current => [...current, userItem, assistantItem]);

      const controller = new AbortController();
      chatAbortRef.current = controller;
      const response = await apiFetch("/conversations/" + encodeURIComponent(targetId) + "/messages/stream", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: question, limit: 5, rerank: rerankEnabled, model_settings: modelSettings.api_key.trim() ? modelSettings : undefined }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "问答请求失败");
      }
      if (!response.body) throw new Error("浏览器不支持流式响应");
      let receivedDone = false;
      for await (const frame of readSSEStream(response.body)) {
        if (frame.event === "sources") {
          const payload = JSON.parse(frame.data) as { sources?: ChatSource[] };
          setChatItems(current => current.map(item => item.id === assistantId ? { ...item, sources: payload.sources || [] } : item));
          setChatStatus("streaming");
        } else if (frame.event === "token") {
          const payload = JSON.parse(frame.data) as { content?: string };
          setChatItems(current => current.map(item => item.id === assistantId ? { ...item, content: item.content + (payload.content || "") } : item));
          setChatStatus("streaming");
        } else if (frame.event === "error") {
          const payload = JSON.parse(frame.data) as { message?: string };
          throw new Error(payload.message || "生成失败");
        } else if (frame.event === "done") {
          receivedDone = true;
          setChatItems(current => current.map(item => item.id === assistantId ? { ...item, streaming: false } : item));
          setChatStatus("completed");
        }
      }
      if (!receivedDone) throw new Error("流式响应意外结束，请重新打开对话确认保存状态。");
      await loadConversations();
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        setChatItems(current => current.map(item => item.streaming ? { ...item, streaming: false } : item));
        setChatStatus("idle");
      } else {
        setChatError(error instanceof Error ? error.message : "问答失败，请重试。");
        setChatStatus("error");
        setChatItems(current => current.map(item => item.streaming ? { ...item, streaming: false } : item));
      }
    } finally {
      chatAbortRef.current = null;
      setChatLoading(false);
      loadConversations().catch(() => undefined);
    }
  };

  const stopGeneration = () => chatAbortRef.current?.abort();

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true); setPageMessage(""); setPageError("");
    const body = new FormData(); body.append("file", file);
    try {
      const response = await apiFetch("/documents", { method: "POST", body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "上传失败");
      setPageMessage("已完成解析与分块：" + result.filename + "，共 " + result.chunk_count + " 个文本块；向量状态：" + (result.embedding_status === "indexed" ? "已建立" : "待配置 Embedding API"));
      await loadDocuments();
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "上传失败，请重试。");
    } finally { setUploading(false); event.target.value = ""; }
  };

  const handleReindex = async () => {
    setReindexing(true); setPageMessage(""); setPageError("");
    try {
      const response = await apiFetch("/documents/reindex", { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "重新生成向量失败");
      await loadDocuments();
      setPageMessage("向量索引完成：" + result.indexed_documents + "/" + result.total_documents + " 份文档成功");
    } catch (error) { setPageError(error instanceof Error ? error.message : "重新生成向量失败"); }
    finally { setReindexing(false); }
  };

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true); setComparison([]);
    const modes = ["keyword", "vector", "hybrid"];
    const outcomes = await Promise.all(modes.map(async mode => {
      try {
        const response = await apiFetch("/search", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: searchQuery.trim(), limit: 5, mode, rerank: mode === "hybrid" && rerankEnabled }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "检索失败");
        return { mode, results: result.results as SearchResult[], fallback: result.mode === "keyword_fallback" ? result.fallback_reason : undefined, reranker: result.reranker, rerankerError: result.reranker_error };
      } catch (error) { return { mode, results: [] as SearchResult[], error: error instanceof Error ? error.message : "检索失败" }; }
    }));
    setComparison(outcomes);
    setSearching(false);
  };

  const handleTestModel = async (config: ModelSettingsValue) => {
    setModelTesting(true); setModelStatus("");
    try {
      const response = await apiFetch("/model/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "模型连接失败");
      setModelStatus(result.message || "模型连接成功");
    } catch (error) { setModelStatus(error instanceof Error ? error.message : "模型连接失败"); }
    finally { setModelTesting(false); }
  };

  const handleCitationClick = (conversationItem: ChatItem, sourceId: number) => {
    const key = conversationItem.id + ":" + sourceId;
    setExpandedSources(current => current.includes(key) ? current : [...current, key]);
    setHighlightedSource(key);
    document.getElementById("source-" + key)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const renderComparison = (item: ComparisonResult) => <div className="comparison-column" key={item.mode}>
    <div className="comparison-heading"><strong>{item.mode === "keyword" ? "关键词检索" : item.mode === "vector" ? "向量语义检索" : "混合检索"}</strong><span>{item.error ? "不可用" : item.results.length + " 条结果"}</span></div>
    {item.error ? <div className="comparison-error"><AlertCircle size={15} />{item.error}</div> : <>
      {item.fallback && <div className="comparison-fallback">{item.fallback}</div>}
      {item.mode === "hybrid" && item.reranker === "applied" && <div className="comparison-success">已启用重排序</div>}
      <div className="result-list">{item.results.map((result, index) => <article className="result-card" key={result.chunk_id}>
        <div className="result-top"><strong>#{index + 1} · {result.filename}</strong><span>片段 #{result.chunk_index + 1} · {result.score.toFixed(4)}</span></div>
        <p>{result.content}</p>
      </article>)}</div>
    </>}
  </div>;

  const activeTitle = conversations.find(item => item.id === activeConversationId)?.title || "新对话";

  return <main className={"shell app-shell" + (sidebarCollapsed ? " sidebar-collapsed" : "")}>
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Bot size={21} /></span>{!sidebarCollapsed && <span>KnowFlow</span>}</div>
      <button className="new-chat-button" onClick={() => createConversation().catch(error => setChatError(error instanceof Error ? error.message : "创建对话失败"))}><Plus size={16} />{!sidebarCollapsed && "新建对话"}</button>
      {!sidebarCollapsed && <>
        <div className="workspace-label">最近对话</div>
        <div className="conversation-list">
          {conversations.length === 0 && <p className="conversation-empty">还没有历史对话</p>}
          {conversations.map(item => <div className={"conversation-entry" + (item.id === activeConversationId ? " active" : "")} key={item.id}>
            <button className="conversation-select" onClick={() => selectConversation(item.id)} title={item.title}>
              <MessageSquare size={15} /><span>{item.title}</span>
            </button>
            <button className="conversation-delete" aria-label="删除对话" title="删除对话" onClick={() => removeConversation(item.id)}><Trash2 size={14} /></button>
          </div>)}
        </div>
        <div className="workspace-label workspace-secondary">工作空间</div>
        <button className={"nav-item" + (activeSection === "chat" ? " active" : "")} onClick={() => setActiveSection("chat")}><Sparkles size={17} /> 智能问答</button>
        <button className={"nav-item" + (activeSection === "documents" ? " active" : "")} onClick={() => setActiveSection("documents")}><FileText size={17} /> 知识库管理</button>
      </>}
      <div className="sidebar-bottom"><div className={"status-dot " + (health === "ok" ? "online" : "")} />{!sidebarCollapsed && <span>API {health === "ok" ? "运行正常" : health === "error" ? "连接失败" : "检查中"}</span>}</div>
      <button className="sidebar-collapse" onClick={() => setSidebarCollapsed(value => !value)} title={sidebarCollapsed ? "展开侧栏" : "收起侧栏"}>{sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}</button>
    </aside>

    <section className="main-panel">
      <header className="topbar">
        <div><span className="eyebrow">ENTERPRISE KNOWLEDGE</span><h1>{activeSection === "chat" ? "企业知识助手" : "知识库管理"}</h1></div>
        <div className="topbar-actions">
          <button className="settings-trigger" onClick={() => setShowModelSettings(value => !value)}><Settings size={15} /> 模型设置</button>
          <div className="secure"><ShieldCheck size={16} /> Session 隔离</div>
        </div>
      </header>
      {showModelSettings && <ModelSettings value={modelSettings} onSave={value => { setModelSettings(value); setModelStatus("配置保存在当前页面内存中，刷新后需要重新输入 API Key。"); }} onClear={() => { setModelSettings({ api_key: "", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-max" }); setModelStatus("模型配置已清除。"); }} onTest={handleTestModel} testing={modelTesting} status={modelStatus} />}

      {activeSection === "chat" ? <section className="conversation-workspace">
        <div className="conversation-heading">
          <div><span className="eyebrow">KNOWLEDGE CHAT</span><h2>{activeTitle}</h2><p>基于企业知识库的连续对话，每轮回答均重新检索并保留来源。</p></div>
          <button className="secondary-action" onClick={() => createConversation().catch(error => setChatError(error instanceof Error ? error.message : "创建对话失败"))}><Plus size={15} /> 新对话</button>
        </div>
        <div className="chat-transcript" aria-live="polite">
          {chatItems.length === 0 && <div className="chat-welcome">
            <div className="welcome-icon"><Sparkles size={22} /></div>
            <h2>有什么企业知识需要了解？</h2>
            <p>你可以连续追问，例如先询问试用期，再追问转正后的年假政策。</p>
            <div className="suggestion-chips">
              <button onClick={() => setChatInput("员工试用期有多长？")}>员工试用期有多长？</button>
              <button onClick={() => setChatInput("出差报销需要在多久内提交？")}>出差报销期限</button>
              <button onClick={() => setChatInput("公司有哪些安全制度？")}>公司安全制度</button>
            </div>
          </div>}
          {chatItems.map(item => <article className={"chat-message " + item.role} key={item.id}>
            <div className="message-avatar">{item.role === "assistant" ? <Bot size={17} /> : <span>你</span>}</div>
            <div className="message-main">
              <div className="message-author">{item.role === "assistant" ? "KnowFlow 助手" : "你"}</div>
              {item.role === "assistant" ? (
                item.content ? <ChatMessage content={item.content} sourceIds={item.sources.map(source => source.id)} onCitationClick={id => handleCitationClick(item, id)} /> :
                  <div className="message-placeholder">{item.streaming ? <><Loader2 className="spin" size={15} /> 正在组织回答…</> : "本轮未生成完整回答。"}</div>
              ) : <div className="user-message-content">{item.content}</div>}
              {item.role === "assistant" && item.sources.length > 0 && <div className="message-sources">
                <div className="sources-heading"><BookOpen size={14} /> 本轮参考来源 · {item.sources.length}</div>
                {item.sources.map(source => {
                  const key = item.id + ":" + source.id;
                  const expanded = expandedSources.includes(key);
                  return <article id={"source-" + key} className={"message-source" + (highlightedSource === key ? " highlighted" : "")} key={key}>
                    <button onClick={() => setExpandedSources(current => expanded ? current.filter(value => value !== key) : [...current, key])}>
                      <span>[{source.id}] {source.filename} · 片段 #{source.chunk_index + 1}</span><span>{expanded ? "收起" : "查看依据"}</span>
                    </button>
                    {expanded && <p>{source.content}</p>}
                  </article>;
                })}
              </div>}
              {item.role === "assistant" && item.streaming && <span className="stream-cursor" />}
            </div>
          </article>)}
          {chatLoading && chatStatus === "connecting" && <div className="chat-connecting"><Loader2 className="spin" size={15} /> 正在连接知识库与模型服务…</div>}
        </div>
        {chatError && <div className="chat-error"><AlertCircle size={15} />{chatError}</div>}
        <form className="chat-composer" onSubmit={handleSend}>
          <textarea ref={chatInputRef} value={chatInput} onChange={event => setChatInput(event.target.value)} onKeyDown={(event: KeyboardEvent<HTMLTextAreaElement>) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void handleSend(); } }} placeholder="向企业知识库提问…（Enter 发送，Shift + Enter 换行）" rows={2} disabled={chatLoading} />
          {chatLoading ? <button type="button" className="stop-button" onClick={stopGeneration}><Square size={14} /> 停止</button> : <button type="submit" disabled={!chatInput.trim()}><Send size={15} /> 发送</button>}
        </form>
        <div className="composer-hint">AI 回答仅以当前检索到的企业文档为依据；历史消息用于理解上下文，不作为事实来源。</div>
      </section> : <section className="documents-workspace">
        <div className="section-heading"><div><h2>知识库文档</h2><p>上传企业资料，构建可检索的知识库。</p></div></div>
        <input ref={uploadRef} className="hidden-input" type="file" accept=".pdf,.docx,.txt,.md" onChange={handleUpload} />
        <button className="upload-box" onClick={() => uploadRef.current?.click()} disabled={uploading}>
          {uploading ? <Loader2 className="spin" size={20} /> : <Upload size={20} />}
          <span>{uploading ? "正在上传、解析与分块…" : "选择文件，上传到知识库"}</span>
          <small>支持 PDF、DOCX、TXT、Markdown，单个文件最大 10 MB</small>
        </button>
        {pageMessage && <div className="notice success"><CheckCircle2 size={16} />{pageMessage}</div>}
        {pageError && <div className="notice error"><AlertCircle size={16} />{pageError}</div>}
        <div className="section-heading document-heading"><div><h3>已上传文档</h3><p>{documents.length} 个文件</p></div><button type="button" onClick={handleReindex} disabled={reindexing || documents.length === 0}>{reindexing ? "正在生成向量…" : "重新生成向量"}</button></div>
        {documents.length === 0 ? <div className="empty-state"><FileText size={23} /><span>还没有文档，上传一份资料开始构建知识库</span></div> :
          <div className="document-list">{documents.map(document => <article className="document-row" key={document.id}>
            <div className="file-icon"><FileText size={19} /></div>
            <div className="file-info"><strong>{document.filename}</strong><span>{formatSize(document.size)} · {document.character_count.toLocaleString()} 字符 · {document.chunk_count} 个片段 · {document.embedded_chunk_count} 个向量</span></div>
            <span className="ready"><CheckCircle2 size={14} />{document.embedded_chunk_count > 0 ? "向量已索引" : "文本已分块"}</span>
          </article>)}</div>}
        <section className="search-section">
          <div className="section-heading"><div><h3>三种检索策略对比</h3><p>对比关键词、向量语义和混合检索结果。</p></div></div>
          <form className="search-form" onSubmit={handleSearch}><Search size={18} /><input value={searchQuery} onChange={event => setSearchQuery(event.target.value)} placeholder="输入用于检索对比的问题…" /><button type="submit" disabled={searching || !searchQuery.trim()}>{searching ? "对比中…" : "同时检索"}</button></form>
          <label className="rerank-toggle"><input type="checkbox" checked={rerankEnabled} onChange={event => setRerankEnabled(event.target.checked)} /> 对混合检索启用 Reranker</label>
          {comparison.length > 0 && <div className="comparison-grid">{comparison.map(renderComparison)}</div>}
        </section>
      </section>}
      <footer className="page-footer"><ShieldCheck size={14} /> 每段对话独立管理；引用来源按消息分别保存。</footer>
    </section>
  </main>;
}
