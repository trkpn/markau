/**
 * @vitest-environment jsdom
 *
 * The importer has to recognise what a URL points at, and it has to turn a
 * page into Markdown that keeps the things a reader needs: the headings,
 * the links, the code, the tables — and none of the navigation.
 */
import { describe, it, expect, vi } from 'vitest';

// The bytes are the subject of the binary tests, not the reader of PDFs —
// the parser stands in, so a test can tell the bytes arrived without
// loading a real one.
vi.mock('@/importers/pdf.js', () => ({
  pdfToMarkdown: vi.fn(async () => ({
    markdown: 'The words of the bytes.',
    title: 'Paper of the Origin',
    pages: 1
  })),
  buildPdfDocument: (pdf) => pdf.markdown,
  fromBase64: () => new Uint8Array()
}));

const { detectSource, normalizeUrl, decodeBase64Utf8, SOURCE } =
  await import('@/app/import/sources.js');
const { htmlToMarkdown, resolveUrl } = await import('@/importers/html.js');
const { buildDocument, importFromUrl, isTextual, stripReaderHeader } = await import(
  '@/app/import/url-import.js'
);

/**
 * The error the browser hands back when a fetch is stopped midway.
 */
function abortError() {
  const err = new Error('This operation was aborted');
  err.name = 'AbortError';
  return err;
}

/**
 * An answer of the origin, as the fetch of a browser would hand it over.
 *
 * @param {string} body the text of the answer
 * @param {object} [details] what else the answer carries
 * @param {string} [details.contentType] the kind of the answer
 * @param {string} [details.url] the address the answer came from
 * @returns {object} a stand-in for a Response
 */
function originResponse(body, { contentType = 'text/html; charset=utf-8', url } = {}) {
  return {
    ok: true,
    status: 200,
    url,
    headers: { get: (name) => (name === 'content-type' ? contentType : null) },
    text: async () => body
  };
}

/**
 * Stands in for the network. By default the origin refuses a direct read
 * and the proxy refuses everything; each test can answer for either leg
 * instead.
 *
 * @param {object} [answers] what the two legs of the ladder answer
 * @param {(address: string) => object|Error|Promise<object|Error>} [answers.origin]
 *   what the origin answers — an object is served, an error is thrown
 * @param {(address: string) => object|Promise<object>} [answers.proxy] the payload of the proxy
 * @returns {{ direct: string[], proxy: string[] }} the addresses each leg saw
 */
function mockFetch({ origin, proxy } = {}) {
  const seen = { direct: [], proxy: [] };

  globalThis.fetch = async (url) => {
    const address = String(url);

    if (address.startsWith('/api/fetch')) {
      seen.proxy.push(address);
      const payload = proxy
        ? await proxy(address)
        : { ok: false, error: 'The proxy could not fetch that page.' };
      return { ok: true, status: 200, json: async () => payload };
    }

    seen.direct.push(address);
    const answer = origin ? await origin(address) : null;
    if (answer instanceof Error) throw answer;
    if (answer) return answer;
    throw new TypeError('Failed to fetch');
  };

  return seen;
}

describe('reading an address', () => {
  it('accepts an address without a scheme', () => {
    expect(normalizeUrl('github.com/owner/repo')?.href).toBe('https://github.com/owner/repo');
  });

  it('refuses something that is not an address', () => {
    expect(normalizeUrl('not a url')).toBeNull();
    expect(normalizeUrl('')).toBeNull();
  });

  it('refuses a scheme that is not http', () => {
    expect(normalizeUrl('javascript:alert(1)')).toBeNull();
    expect(normalizeUrl('file:///etc/passwd')).toBeNull();
  });
});

describe('knowing the source', () => {
  it('sees a GitHub repository', () => {
    const source = detectSource('https://github.com/owner/repository');

    expect(source.type).toBe(SOURCE.GITHUB_REPO);
    expect(source.owner).toBe('owner');
    expect(source.repo).toBe('repository');
  });

  it('sees a file inside a GitHub repository', () => {
    const source = detectSource('https://github.com/owner/repository/blob/main/docs/guide.md');

    expect(source.type).toBe(SOURCE.GITHUB_FILE);
    expect(source.ref).toBe('main');
    expect(source.path).toBe('docs/guide.md');
  });

  it('does not mistake a GitHub listing for a repository', () => {
    expect(detectSource('https://github.com/topics/markdown')?.type).toBe(SOURCE.WEB_PAGE);
    expect(detectSource('https://github.com/settings/profile')?.type).toBe(SOURCE.WEB_PAGE);
  });

  it('sees a Hugging Face model', () => {
    const source = detectSource('https://huggingface.co/some-org/some-model');

    expect(source.type).toBe(SOURCE.HF_MODEL);
    expect(source.id).toBe('some-org/some-model');
  });

  it('sees a Hugging Face dataset and a Space', () => {
    expect(detectSource('https://huggingface.co/datasets/some-org/some-set')?.type).toBe(
      SOURCE.HF_DATASET
    );
    expect(detectSource('https://huggingface.co/spaces/some-org/some-space')?.type).toBe(
      SOURCE.HF_SPACE
    );
  });

  it('sees a Markdown file', () => {
    expect(detectSource('https://example.com/notes/readme.md')?.type).toBe(SOURCE.RAW_MARKDOWN);
    expect(detectSource('https://example.com/notes/readme.MARKDOWN')?.type).toBe(
      SOURCE.RAW_MARKDOWN
    );
  });

  it('sees anything else as a page to read', () => {
    expect(detectSource('https://example.com/some/article')?.type).toBe(SOURCE.WEB_PAGE);
  });

  it('sees a YouTube video', () => {
    expect(detectSource('https://www.youtube.com/watch?v=dQw4w9WgXcQ')?.videoId).toBe(
      'dQw4w9WgXcQ'
    );
    expect(detectSource('https://youtu.be/dQw4w9WgXcQ')?.videoId).toBe('dQw4w9WgXcQ');
    expect(detectSource('https://www.youtube.com/shorts/abc123')?.videoId).toBe('abc123');
    expect(detectSource('https://www.youtube.com/embed/abc123')?.videoId).toBe('abc123');
    expect(detectSource('https://www.youtube.com/watch?v=dQw4w9WgXcQ')?.type).toBe(
      SOURCE.YOUTUBE_VIDEO
    );
  });

  it('sees a YouTube playlist', () => {
    const source = detectSource('https://www.youtube.com/playlist?list=PL123');

    expect(source.type).toBe(SOURCE.YOUTUBE_PLAYLIST);
    expect(source.listId).toBe('PL123');
  });

  it('sees a Substack post', () => {
    const source = detectSource('https://blog.example.substack.com/p/some-post');

    expect(source.type).toBe(SOURCE.SUBSTACK_POST);
    expect(source.publication).toBe('blog.example.substack.com');
  });

  it('leaves the home page of a publication as a page', () => {
    expect(detectSource('https://blog.example.substack.com/')?.type).toBe(SOURCE.WEB_PAGE);
  });

  it('sees a Reddit thread', () => {
    const source = detectSource('https://www.reddit.com/r/programming/comments/abc123/a_post/');

    expect(source.type).toBe(SOURCE.REDDIT_THREAD);
    expect(source.subreddit).toBe('programming');
    expect(source.id).toBe('abc123');
  });
});

describe('decoding what GitHub sends', () => {
  it('turns the base64 payload into the text of the file', () => {
    const text = '# Title\n\nSome text with Thai: สวัสดี';
    const encoded = Buffer.from(text, 'utf8').toString('base64');

    expect(decodeBase64Utf8(encoded)).toBe(text);
  });

  it('survives the line breaks GitHub puts in the payload', () => {
    const encoded = Buffer.from('hello', 'utf8').toString('base64');
    const broken = encoded.replace(/(.{4})/g, '$1\n');

    expect(decodeBase64Utf8(broken)).toBe('hello');
  });
});

describe('resolving links', () => {
  it('makes a relative link absolute', () => {
    expect(resolveUrl('/about', 'https://example.com/post/1')).toBe('https://example.com/about');
    expect(resolveUrl('other', 'https://example.com/post/1')).toBe(
      'https://example.com/post/other'
    );
  });

  it('leaves an absolute link alone', () => {
    expect(resolveUrl('https://other.example/x', 'https://example.com/')).toBe(
      'https://other.example/x'
    );
  });
});

describe('putting the document together', () => {
  it('knows what can be read and what cannot', () => {
    expect(isTextual('text/html; charset=utf-8')).toBe(true);
    expect(isTextual('application/xhtml+xml')).toBe(true);
    expect(isTextual('application/xml')).toBe(true);
    expect(isTextual('')).toBe(true);

    expect(isTextual('application/pdf')).toBe(false);
    expect(isTextual('application/vnd.openxmlformats-officedocument.wordprocessingml.document')).toBe(
      false
    );
    expect(isTextual('image/png')).toBe(false);
    expect(isTextual('video/mp4')).toBe(false);
    expect(isTextual('application/zip')).toBe(false);
  });

  it('takes the header of the reader service off the answer', () => {
    const answer = `Title: The page

URL Source: https://example.com/page

Published Time: Jan 1, 2024

Markdown Content:
The text of the page.`;

    expect(stripReaderHeader(answer)).toBe('The text of the page.');
    expect(stripReaderHeader('Just the text.')).toBe('Just the text.');
  });

  it('writes a header that says where the document came from', () => {
    const document = buildDocument({
      markdown: '# The Article\n\nBody',
      title: 'The Article',
      sourceUrl: 'https://example.com/post'
    });

    expect(document).toContain('title: The Article');
    expect(document).toContain('source: https://example.com/post');
    expect(document).toContain('# The Article');
  });

  it('merges the header of the document into the one of the import', () => {
    const document = buildDocument({
      markdown: '---\nlanguage: en\nlicense: mit\n---\n\n# The Model Card',
      title: 'some-model',
      sourceUrl: 'https://huggingface.co/some-model'
    });

    expect(document).toContain('language: en');
    expect(document).toContain('license: mit');
    expect(document).toContain('title: some-model');

    // The block of the document must not be left inside the text.
    expect(document.match(/^---$/gm)).toHaveLength(2);
  });

  it('lets the document keep its own title', () => {
    const document = buildDocument({
      markdown: '---\ntitle: The Real Title\n---\n\nBody',
      title: 'some-model',
      sourceUrl: 'https://huggingface.co/some-model'
    });

    expect(document).toContain('title: The Real Title');
    expect(document).not.toContain('title: some-model');
  });
});

describe('turning a page into Markdown', () => {
  const page = `
    <!doctype html>
    <html>
      <head><title>The Article</title></head>
      <body>
        <nav><a href="/home">Home</a><a href="/about">About</a></nav>
        <header><h1 class="site-name">The News Site</h1></header>
        <main>
          <article>
            <h1>The Article</h1>
            <p>This is the opening paragraph of the article, and it is long enough for the
               reader to consider it a real piece of writing.</p>
            <p>A second paragraph with a <a href="/other/story">link inside</a> and some
               <strong>bold words</strong> as well as <em>italic ones</em>.</p>
            <h2>A section</h2>
            <ul><li>first item</li><li>second item</li></ul>
            <pre><code class="language-js">const answer = 42;</code></pre>
            <table>
              <thead><tr><th>Name</th><th>Value</th></tr></thead>
              <tbody><tr><td>alpha</td><td>1</td></tr></tbody>
            </table>
            <figure>
              <img src="/images/photo.jpg" alt="A photo" />
              <figcaption>The caption</figcaption>
            </figure>
          </article>
        </main>
        <aside class="advert"><p>Buy something now, this is an advert.</p></aside>
        <footer><p>Copyright nobody</p></footer>
      </body>
    </html>
  `;

  it('keeps the heading of the article', async () => {
    const { markdown } = await htmlToMarkdown(page, 'https://news.example/post/1');

    expect(markdown).toContain('# The Article');
  });

  it('keeps the text of the article', async () => {
    const { markdown } = await htmlToMarkdown(page, 'https://news.example/post/1');

    expect(markdown).toContain('opening paragraph of the article');
  });

  it('makes a relative link absolute', async () => {
    const { markdown } = await htmlToMarkdown(page, 'https://news.example/post/1');

    expect(markdown).toContain('https://news.example/other/story');
  });

  it('keeps the code block with its language', async () => {
    const { markdown } = await htmlToMarkdown(page, 'https://news.example/post/1');

    expect(markdown).toContain('```js');
    expect(markdown).toContain('const answer = 42;');
  });

  it('keeps the table as a table', async () => {
    const { markdown } = await htmlToMarkdown(page, 'https://news.example/post/1');

    expect(markdown).toContain('| Name');
    expect(markdown).toContain('alpha');
  });

  it('makes the image absolute', async () => {
    const { markdown } = await htmlToMarkdown(page, 'https://news.example/post/1');

    expect(markdown).toContain('https://news.example/images/photo.jpg');
  });

  it('leaves the navigation and the adverts out', async () => {
    const { markdown } = await htmlToMarkdown(page, 'https://news.example/post/1');

    expect(markdown).not.toContain('Buy something now');
    expect(markdown).not.toContain('Copyright nobody');
  });

  it('does not run the scripts of the page', async () => {
    const { markdown } = await htmlToMarkdown(
      '<html><body><script>window.hacked = true</script><p>Text of the page that is long enough.</p></body></html>',
      'https://example.com/'
    );

    expect(markdown).not.toContain('hacked');
  });

  it('keeps a list inside a table cell from breaking the table', async () => {
    const { markdown } = await htmlToMarkdown(
      `<html><body><article>
         <p>A paragraph that is long enough for the reader to treat this as an article.</p>
         <table>
           <thead><tr><th>Field</th><th>Authors</th></tr></thead>
           <tbody><tr><td>Written by</td><td><ul><li>First</li><li>Second</li></ul></td></tr></tbody>
         </table>
       </article></body></html>`,
      'https://example.com/'
    );

    // The row has to stay one row: no marker of a list may end it, and no
    // line break may split it in two.
    const rows = markdown.split('\n').filter((line) => line.trim().startsWith('|'));
    expect(rows).toHaveLength(3);
    expect(rows[2]).toBe('| Written by | First Second |');
  });
});

describe('cancelling an import', () => {
  it('does not ask the proxy for an import that was stopped', async () => {
    const seen = mockFetch({
      origin: () => abortError(),
      proxy: () => ({
        ok: true,
        status: 200,
        finalUrl: 'https://example.com/notes/readme.md',
        contentType: 'text/plain',
        body: '# The answer of the proxy'
      })
    });

    const error = await importFromUrl('https://example.com/notes/readme.md').then(
      () => null,
      (err) => err
    );

    // A cancelled import is not an error to fall back from: the call stops
    // with the abort itself, and the proxy never hears of the address.
    expect(error?.name).toBe('AbortError');
    expect(seen.proxy).toHaveLength(0);
  });
});

describe('falling back to the proxy', () => {
  const articlePage = `
    <!doctype html>
    <html>
      <head><title>The Article of the Proxy</title></head>
      <body>
        <main>
          <article>
            <h1>The Article of the Proxy</h1>
            <p>This is the opening paragraph of the article, and it is long enough for the
               reader to consider it a real piece of writing rather than the empty shell
               of a page that draws itself with a script of its own.</p>
            <p>A second paragraph carries the words that only a proper answer would hold,
               so the test can tell that the words of the page were served and turned
               into a document for the reader who asked for them.</p>
            <p>A third paragraph rounds the article out, so the reader finds a piece of
               writing with a body worth the name and not a fragment of one.</p>
          </article>
        </main>
      </body>
    </html>
  `;

  it('serves a Markdown file straight from the origin', async () => {
    const seen = mockFetch({
      origin: () =>
        originResponse('# The Notes of the Origin\n\nThe words of the file.', {
          contentType: 'text/plain',
          url: 'https://example.com/notes/readme.md'
        })
    });

    const result = await importFromUrl('https://example.com/notes/readme.md');

    expect(seen.direct).toHaveLength(1);
    expect(seen.proxy).toHaveLength(0);
    expect(result.markdown).toContain('words of the file');
    expect(result.note).toBe('Markdown file');
  });

  it('reads a Markdown file through the proxy when the origin refuses', async () => {
    const seen = mockFetch({
      proxy: () => ({
        ok: true,
        status: 200,
        finalUrl: 'https://example.com/notes/readme.md',
        contentType: 'text/plain',
        body: '# The Proxied Notes\n\nThe words that came through the proxy.'
      })
    });

    const result = await importFromUrl('https://example.com/notes/readme.md');

    expect(seen.direct).toHaveLength(1);
    expect(seen.proxy).toHaveLength(1);
    expect(result.markdown).toContain('words that came through the proxy');
    expect(result.note).toBe('Markdown file');
  });

  it('serves a page straight from the origin', async () => {
    const seen = mockFetch({
      origin: () => originResponse(articlePage, { url: 'https://example.com/some/article' })
    });

    const result = await importFromUrl('https://example.com/some/article');

    expect(seen.proxy).toHaveLength(0);
    expect(result.markdown).toContain('The Article of the Proxy');
    expect(result.note).toBe('article');
  });

  it('serves a file of bytes straight from the origin', async () => {
    const seen = mockFetch({
      origin: () => ({
        ok: true,
        status: 200,
        url: 'https://example.com/files/paper.pdf',
        headers: { get: (name) => (name === 'content-type' ? 'application/pdf' : null) },
        // No stream on the stand-in, so the bytes arrive as one buffer.
        arrayBuffer: async () => new TextEncoder().encode('%PDF bytes of the origin').buffer
      })
    });

    const result = await importFromUrl('https://example.com/files/paper.pdf');

    expect(seen.direct).toHaveLength(1);
    expect(seen.proxy).toHaveLength(0);
    expect(result.markdown).toContain('words of the bytes');
    expect(result.note).toBe('PDF (1 pages)');
  });

  it('reads a page through the proxy when the origin refuses', async () => {
    const seen = mockFetch({
      proxy: () => ({
        ok: true,
        status: 200,
        finalUrl: 'https://example.com/some/article',
        contentType: 'text/html; charset=utf-8',
        body: articlePage
      })
    });

    const result = await importFromUrl('https://example.com/some/article');

    expect(seen.direct).toHaveLength(1);
    expect(seen.proxy).toHaveLength(1);
    expect(result.markdown).toContain('The Article of the Proxy');
    expect(result.note).toBe('article (via the proxy)');
  });

  it('does not ask the proxy again for an answer that is not a page of text', async () => {
    const seen = mockFetch({
      origin: () => originResponse('%PDF- not really a page', { contentType: 'application/pdf' })
    });

    // A post of Substack goes straight through the ladder: nothing of the
    // app may follow a definitive answer of the origin.
    const error = await importFromUrl('https://blog.example.substack.com/p/some-post').then(
      () => null,
      (err) => err
    );

    expect(seen.direct).toHaveLength(1);
    expect(seen.proxy).toHaveLength(0);
    expect(error?.message).toBe('That address is not a page of text.');
  });

  it('reads the JSON of a Reddit thread through the proxy', async () => {
    const thread = [
      {
        data: {
          children: [
            {
              kind: 't3',
              data: {
                title: 'The Post of the Thread',
                subreddit: 'programming',
                author: 'someone',
                score: 42,
                created_utc: 1730000000,
                is_self: true,
                selftext:
                  'The body of the post, long enough to stand as a document on its own once the thread is built and shown to the reader who asked for it.',
                permalink: '/r/programming/comments/abc123/a_post/'
              }
            }
          ]
        }
      }
    ];

    const seen = mockFetch({
      proxy: () => ({
        ok: true,
        status: 200,
        finalUrl: 'https://www.reddit.com/r/programming/comments/abc123/a_post/.json',
        contentType: 'application/json',
        body: JSON.stringify(thread)
      })
    });

    const result = await importFromUrl(
      'https://www.reddit.com/r/programming/comments/abc123/a_post/'
    );

    expect(seen.direct).toHaveLength(1);
    expect(seen.proxy).toHaveLength(1);
    expect(result.markdown).toContain('# The Post of the Thread');
    expect(result.note).toBe('thread');
  });

  it('reports a refusal of the proxy as the answer of the address', async () => {
    const seen = mockFetch({
      proxy: () => ({ ok: true, status: 404, finalUrl: 'https://example.com/files/paper.pdf' })
    });

    const error = await importFromUrl('https://example.com/files/paper.pdf').then(
      () => null,
      (err) => err
    );

    expect(seen.direct).toHaveLength(1);
    expect(seen.proxy).toHaveLength(1);
    expect(error?.message).toBe('That address answered 404.');
  });
});
