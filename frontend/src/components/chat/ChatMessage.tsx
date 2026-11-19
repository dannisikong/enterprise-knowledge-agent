import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";

type ChatMessageProps = {
  content: string;
};

export default function ChatMessage({ content }: ChatMessageProps) {
  return (
    <div className="answer-content markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: false }]]}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
