(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function inlineMarkdown(value) {
    const code = [];
    let text = escapeHtml(value).replace(/`([^`]+)`/g, (_match, content) => {
      const key = `\u0000CODE${code.length}\u0000`;
      code.push(`<code>${content}</code>`);
      return key;
    });

    text = text
      // 还原 Markdown 的反斜杠转义，但保留普通反斜杠（例如 6\\60）不动。
      .replace(/\\([\\`*_[\]{}()#+.!-])/g, "$1")
      .replace(/\[([^\]]+)]\(([^)]+)\)/g, (_match, label, href) => {
        const decodedHref = href.replaceAll("&amp;", "&");
        const safe = /^(https?:\/\/|\/)/i.test(decodedHref) ? href : "#";
        return `<a href="${safe}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      })
      // 兼容本地模型偶发输出的 **内容*（少一个结束星号）。
      .replace(/(^|[^*])\*\*([^*\n]+?)\*{1,2}/g, "$1<strong>$2</strong>")
      .replace(/(^|[^_])__([^_\n]+?)_{1,2}/g, "$1<strong>$2</strong>")
      .replace(/~~([^~]+)~~/g, "<del>$1</del>")
      .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");

    return code.reduce((result, item, index) => result.replace(`\u0000CODE${index}\u0000`, item), text);
  }

  function isTableDivider(line) {
    const cells = line.trim().replace(/^\||\|$/g, "").split("|").map(cell => cell.trim());
    return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
  }

  function tableCells(line) {
    return line.trim().replace(/^\||\|$/g, "").split("|").map(cell => cell.trim());
  }

  function renderTable(lines, start) {
    const headers = tableCells(lines[start]);
    const rows = [];
    let cursor = start + 2;
    while (cursor < lines.length && lines[cursor].includes("|") && lines[cursor].trim()) {
      rows.push(tableCells(lines[cursor]));
      cursor += 1;
    }
    const head = `<thead><tr>${headers.map(cell => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead>`;
    const body = `<tbody>${rows.map(row => `<tr>${headers.map((_header, index) => `<td>${inlineMarkdown(row[index] || "")}</td>`).join("")}</tr>`).join("")}</tbody>`;
    return { html: `<div class="md-table-wrap"><table>${head}${body}</table></div>`, next: cursor };
  }

  function renderMarkdown(markdown) {
    const lines = String(markdown || "").replaceAll("\r\n", "\n").split("\n");
    const output = [];
    let paragraph = [];
    let cursor = 0;

    function flushParagraph() {
      if (!paragraph.length) return;
      output.push(`<p>${paragraph.map(inlineMarkdown).join("<br>")}</p>`);
      paragraph = [];
    }

    while (cursor < lines.length) {
      const line = lines[cursor];
      const trimmed = line.trim();

      if (trimmed.startsWith("```")) {
        flushParagraph();
        const language = trimmed.slice(3).replace(/[^a-z0-9_-]/gi, "");
        const code = [];
        cursor += 1;
        while (cursor < lines.length && !lines[cursor].trim().startsWith("```")) {
          code.push(lines[cursor]);
          cursor += 1;
        }
        if (cursor < lines.length) cursor += 1;
        output.push(`<pre><code${language ? ` data-language="${language}"` : ""}>${escapeHtml(code.join("\n"))}</code></pre>`);
        continue;
      }

      if (cursor + 1 < lines.length && line.includes("|") && isTableDivider(lines[cursor + 1])) {
        flushParagraph();
        const table = renderTable(lines, cursor);
        output.push(table.html);
        cursor = table.next;
        continue;
      }

      const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed);
      if (heading) {
        flushParagraph();
        const level = heading[1].length;
        output.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
        cursor += 1;
        continue;
      }

      if (/^([-*_])\1\1+$/.test(trimmed.replaceAll(" ", ""))) {
        flushParagraph();
        output.push("<hr>");
        cursor += 1;
        continue;
      }

      if (trimmed.startsWith("> ")) {
        flushParagraph();
        const quote = [];
        while (cursor < lines.length && lines[cursor].trim().startsWith(">")) {
          quote.push(lines[cursor].trim().replace(/^>\s?/, ""));
          cursor += 1;
        }
        output.push(`<blockquote>${quote.map(inlineMarkdown).join("<br>")}</blockquote>`);
        continue;
      }

      const unordered = /^[-+*]\s+(.+)$/.exec(trimmed);
      const ordered = /^\d+[.)]\s+(.+)$/.exec(trimmed);
      if (unordered || ordered) {
        flushParagraph();
        const tag = ordered ? "ol" : "ul";
        const items = [];
        while (cursor < lines.length) {
          const item = ordered
            ? /^\d+[.)]\s+(.+)$/.exec(lines[cursor].trim())
            : /^[-+*]\s+(.+)$/.exec(lines[cursor].trim());
          if (!item) break;
          items.push(`<li>${inlineMarkdown(item[1])}</li>`);
          cursor += 1;
        }
        output.push(`<${tag}>${items.join("")}</${tag}>`);
        continue;
      }

      if (!trimmed) {
        flushParagraph();
        cursor += 1;
        continue;
      }

      paragraph.push(line);
      cursor += 1;
    }

    flushParagraph();
    return output.join("");
  }

  function trimPartialTag(value, tag) {
    const lower = value.toLowerCase();
    for (let length = tag.length - 1; length > 0; length -= 1) {
      if (lower.endsWith(tag.slice(0, length))) return value.slice(0, -length);
    }
    return value;
  }

  function splitThinkSections(rawValue) {
    const raw = String(rawValue || "");
    const lower = raw.toLowerCase();
    const openTag = "<think>";
    const closeTag = "</think>";
    let answer = "";
    let thinking = "";
    let cursor = 0;
    let inThink = false;

    while (cursor < raw.length) {
      const open = lower.indexOf(openTag, cursor);
      if (open < 0) {
        answer += raw.slice(cursor);
        break;
      }
      answer += raw.slice(cursor, open);
      const contentStart = open + openTag.length;
      const close = lower.indexOf(closeTag, contentStart);
      if (close < 0) {
        thinking += raw.slice(contentStart);
        inThink = true;
        cursor = raw.length;
        break;
      }
      thinking += `${thinking ? "\n\n" : ""}${raw.slice(contentStart, close)}`;
      cursor = close + closeTag.length;
    }

    if (!inThink) answer = trimPartialTag(answer, openTag);
    return { answer: answer.replace(/^\s+/, ""), thinking: thinking.trim(), inThink };
  }

  window.MaterialMarkdown = { renderMarkdown, splitThinkSections };
})();
