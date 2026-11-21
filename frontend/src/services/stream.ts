export type SSEMessage = {
  event: string;
  data: string;
};

function createMessage(event: string, data: string[]): SSEMessage | null {
  if (data.length === 0) return null;
  return { event: event || "message", data: data.join("\n") };
}

/** Parse SSE frames without assuming network chunks align with UTF-8 or event boundaries. */
export async function* readSSEStream(stream: ReadableStream<Uint8Array>): AsyncGenerator<SSEMessage> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "";
  let dataLines: string[] = [];
  let firstLine = true;

  const processLine = (rawLine: string): SSEMessage | null => {
    const line = firstLine ? rawLine.replace(/^\uFEFF/, "") : rawLine;
    firstLine = false;
    if (line === "") {
      const message = createMessage(eventName, dataLines);
      eventName = "";
      dataLines = [];
      return message;
    }
    if (line.startsWith(":")) return null;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") eventName = value;
    if (field === "data") dataLines.push(value);
    return null;
  };

  const extractMessages = function* (flush: boolean): Generator<SSEMessage> {
    while (buffer.length > 0) {
      const lf = buffer.indexOf("\n");
      const cr = buffer.indexOf("\r");
      const boundary = lf !== -1 && cr !== -1 ? Math.min(lf, cr) : Math.max(lf, cr);
      if (boundary === -1) break;
      if (buffer[boundary] === "\r" && boundary === buffer.length - 1 && !flush) break;
      const delimiterLength = buffer[boundary] === "\r" && buffer[boundary + 1] === "\n" ? 2 : 1;
      const line = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + delimiterLength);
      const message = processLine(line);
      if (message) yield message;
    }
    if (flush && buffer.length > 0) {
      const message = processLine(buffer);
      buffer = "";
      if (message) yield message;
    }
    if (flush) {
      const message = createMessage(eventName, dataLines);
      eventName = "";
      dataLines = [];
      if (message) yield message;
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      yield* extractMessages(done);
      if (done) break;
    }
  } finally {
    reader.releaseLock();
  }
}
