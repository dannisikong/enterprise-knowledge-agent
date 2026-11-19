import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";

type ChatMessageProps = {
  content: string;
  sourceIds: number[];
  onCitationClick: (sourceId: number) => void;
};

function remarkCitationLinks(options: { sourceIds: number[] }) {
  const validSourceIds = new Set(options.sourceIds);
  return (tree: any) => {
    const transform = (node: any): any[] => {
      if (node.type === "link" || node.type === "linkReference" ||
          node.type === "inlineCode" || node.type === "code" ||
          node.type === "html") {
        return [node];
      }
      if (node.type === "text" && typeof node.value === "string") {
        const parts: any[] = [];
        const pattern = /\[(\d+)\]/g;
        let lastIndex = 0;
        for (const match of node.value.matchAll(pattern)) {
          const index = match.index ?? 0;
          const sourceId = Number(match[1]);
          if (!validSourceIds.has(sourceId)) continue;
          if (index > lastIndex) {
            parts.push({ type: "text", value: node.value.slice(lastIndex, index) });
          }
          parts.push({
            type: "link",
            url: `#source-${sourceId}`,
            children: [{ type: "text", value: match[0] }],
          });
          lastIndex = index + match[0].length;
        }
        if (parts.length > 0) {
          if (lastIndex < node.value.length) {
            parts.push({ type: "text", value: node.value.slice(lastIndex) });
          }
          return parts;
        }
        return [node];
      }
      if (Array.isArray(node.children)) {
        node.children = node.children.flatMap(transform);
      }
      return [node];
    };
    if (Array.isArray(tree.children)) {
      tree.children = tree.children.flatMap(transform);
    }
  };
}

export default function ChatMessage({
  content,
  sourceIds,
  onCitationClick,
}: ChatMessageProps) {
  return (
    <div className="answer-content markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, [remarkCitationLinks, { sourceIds }]]}
        rehypePlugins={[[rehypeHighlight, { detect: false }]]}
        components={{
          a: ({ href, children, ...props }) => {
            const match = href?.match(/^#source-(\d+)$/);
            const sourceId = match ? Number(match[1]) : null;
            return (
              <a
                {...props}
                href={href}
                onClick={(event) => {
                  if (sourceId !== null && sourceIds.includes(sourceId)) {
                    event.preventDefault();
                    onCitationClick(sourceId);
                  }
                }}
              >
                {children}
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
