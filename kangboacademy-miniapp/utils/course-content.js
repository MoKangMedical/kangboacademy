// APIs may return a full HTML page, or a fragment cut off before the exercises.
function extractCourseBody(value) {
 const html = String(value || '')
 .replace(/<!--[\s\S]*?-->/g, '')
 .replace(/<script\b[\s\S]*?<\/script>/gi, '')
 .replace(/<style\b[\s\S]*?<\/style>/gi, '')
 .replace(/<head\b[\s\S]*?<\/head>/gi, '');
 const tags = /<\/?([a-z][\w:-]*)\b(?:[^>"']|"[^"]*"|'[^']*')*>/gi;
 let match;
 let root = '';
 let start = -1;
 let depth = 0;
 while ((match = tags.exec(html))) {
 const tag = match[1].toLowerCase();
 const closing = /^<\//.test(match[0]);
 if (start < 0 && !closing) {
 const classes = match[0].match(/\sclass\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i);
 const isContent = tag === 'div' && classes && (classes[1] || classes[2] || classes[3] || '').split(/\s+/).includes('content');
 if (tag === 'article' || isContent) {
 root = tag;
 start = tags.lastIndex;
 depth = 1;
 }
 } else if (start >= 0 && tag === root) {
 depth += closing ? -1 : 1;
 if (!depth) return unwrapDocumentTags(html.slice(start, match.index));
 }
 }
 if (start >= 0) return unwrapDocumentTags(html.slice(start));
 const body = html.match(/<body\b[^>]*>([\s\S]*?)(?:<\/body>|$)/i);
 return unwrapDocumentTags(body ? body[1] : html);
}

function unwrapDocumentTags(html) {
 return html
 .replace(/<!doctype[^>]*>/gi, '')
 .replace(/<(?:meta|link)\b[^>]*>/gi, '')
 .replace(/<title\b[\s\S]*?<\/title>/gi, '')
 .replace(/<\/?(?:html|head|body|main|article|section|header|footer|nav)\b[^>]*>/gi, '')
 .trim();
}

function sanitizeCourseImages(html) {
 const origin = 'https://kangboacademy.cn';
 return String(html || '').replace(/<img\b[^>]*>/gi, tag => {
 const match = tag.match(/\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i);
 if (!match) return '';
 let src = (match[1] || match[2] || match[3] || '').replace(/&amp;/gi, '&').trim();
 if (!src || /[\s<>"'`\\]/.test(src)) return '';
 if (src.startsWith('//')) src = `https:${src}`;
 else if (src.startsWith('/')) src = origin + src;
 else if (!/^[a-z][a-z\d+.-]*:/i.test(src)) src = `${origin}/${src.replace(/^\.\//, '')}`;
 // Only the already configured first-party domain; no event handlers or srcset.
 if (!src.startsWith(`${origin}/`)) return '';
 return `<img src="${src.replace(/&/g, '&amp;')}" style="max-width:100%;height:auto;display:block;margin:16px auto;" />`;
 });
}

module.exports = { extractCourseBody, sanitizeCourseImages };
