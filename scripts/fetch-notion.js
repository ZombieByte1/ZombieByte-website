const { Client } = require('@notionhq/client');
const fs = require('fs');
const path = require('path');

const notion = new Client({ auth: process.env.NOTION_TOKEN });
const DB_ID  = process.env.NOTION_DATABASE_ID;

/* ── helpers ──────────────────────────────────────── */
function prop(page, name, type) {
    const p = page.properties[name];
    if (!p) return '';
    if (type === 'title')    return p.title?.map(t => t.plain_text).join('') || '';
    if (type === 'text')     return p.rich_text?.map(t => t.plain_text).join('') || '';
    if (type === 'date')     return p.date?.start || '';
    if (type === 'checkbox') return p.checkbox || false;
    if (type === 'select')   return p.select?.name || '';
    if (type === 'multi')    return p.multi_select?.map(s => s.name) || [];
    return '';
}

function richTextToHtml(arr = []) {
    return arr.map(rt => {
        let text = rt.plain_text || '';
        if (rt.annotations?.bold)          text = `<strong>${text}</strong>`;
        if (rt.annotations?.italic)        text = `<em>${text}</em>`;
        if (rt.annotations?.strikethrough) text = `<s>${text}</s>`;
        if (rt.annotations?.code)          text = `<code>${text}</code>`;
        if (rt.href)                       text = `<a href="${rt.href}" target="_blank">${text}</a>`;
        return text;
    }).join('');
}

function blockToHtml(block) {
    const b  = block[block.type] || {};
    const rt = richTextToHtml(b.rich_text);
    switch (block.type) {
        case 'paragraph':           return rt ? `<p class="post-p">${rt}</p>` : '<br>';
        case 'heading_1':           return `<h2 class="post-h1">${rt}</h2>`;
        case 'heading_2':           return `<h3 class="post-h2">${rt}</h3>`;
        case 'heading_3':           return `<h4 class="post-h3">${rt}</h4>`;
        case 'bulleted_list_item':  return `<li class="post-li bullet">${rt}</li>`;
        case 'numbered_list_item':  return `<li class="post-li number">${rt}</li>`;
        case 'quote':               return `<blockquote class="post-quote">${rt}</blockquote>`;
        case 'divider':             return `<hr class="pixel-divider">`;
        case 'callout': {
            const icon = b.icon?.emoji ? b.icon.emoji + ' ' : '';
            return `<div class="post-callout">${icon}${rt}</div>`;
        }
        case 'code': {
            const code = (b.rich_text || []).map(r => r.plain_text).join('');
            return `<pre class="post-code"><code>${code}</code></pre>`;
        }
        case 'image': {
            const src = b.type === 'external' ? b.external.url : b.file.url;
            const cap = richTextToHtml(b.caption);
            return `<figure class="post-figure">
                <img src="${src}" alt="${cap || 'image'}" class="post-img">
                ${cap ? `<figcaption class="post-caption">${cap}</figcaption>` : ''}
            </figure>`;
        }
        case 'video': {
            const vsrc = b.type === 'external' ? b.external.url : '';
            if (vsrc.includes('youtube') || vsrc.includes('youtu.be')) {
                const vid = new URL(vsrc).searchParams.get('v') || vsrc.split('/').pop();
                return `<div class="video-embed-box">
                    <iframe src="https://www.youtube.com/embed/${vid}" allowfullscreen></iframe>
                </div>`;
            }
            return `<a href="${vsrc}" class="read-more" target="_blank">▶ Watch Video</a>`;
        }
        default: return '';
    }
}

function wrapLists(blocks) {
    let html = '', inUl = false, inOl = false;
    for (const b of blocks) {
        if (b.type === 'bulleted_list_item') {
            if (!inUl) { html += '<ul class="post-ul">'; inUl = true; }
            if (inOl)  { html += '</ol>'; inOl = false; }
        } else if (b.type === 'numbered_list_item') {
            if (!inOl) { html += '<ol class="post-ol">'; inOl = true; }
            if (inUl)  { html += '</ul>'; inUl = false; }
        } else {
            if (inUl) { html += '</ul>'; inUl = false; }
            if (inOl) { html += '</ol>'; inOl = false; }
        }
        html += blockToHtml(b);
    }
    if (inUl) html += '</ul>';
    if (inOl) html += '</ol>';
    return html;
}

/* ── main ─────────────────────────────────────────── */
async function main() {
    // 1. Query all published posts from the database
    const response = await notion.databases.query({
        database_id: DB_ID,
        filter: { property: 'published', checkbox: { equals: true } },
        sorts: [{ property: 'date', direction: 'descending' }]
    });

    const posts = [];
    fs.mkdirSync('posts', { recursive: true });

    for (const page of response.results) {
        const slug     = prop(page, 'slug', 'text') || page.id;
        const titleEn  = prop(page, 'Title', 'title');
        const titleEs  = prop(page, 'title_es', 'text');
        const date     = prop(page, 'date', 'date');
        const excerptEn = prop(page, 'excerpt_en', 'text');
        const excerptEs = prop(page, 'excerpt_es', 'text');
        const thumbnail = prop(page, 'thumbnail', 'text');
        const tags      = prop(page, 'tags', 'multi');

        // Format display dates
        const d = date ? new Date(date) : null;
        const dateEn = d ? d.toLocaleDateString('en-US', { year:'numeric', month:'long', day:'2-digit' }) : '';
        const dateEs = d ? d.toLocaleDateString('es-MX', { year:'numeric', month:'long', day:'2-digit' }) : '';

        // 2. Fetch all blocks (post body content)
        const blocksRes = await notion.blocks.children.list({
            block_id: page.id,
            page_size: 100
        });

        const bodyHtml = wrapLists(blocksRes.results);

        // 3. Write individual post HTML file
        const postHtml = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZombieByte | ${titleEn}</title>
    <link rel="icon" href="/placeholder_zombiebyte_favicon_skull.ico">
    <link rel="stylesheet" href="/assets/style.css">
</head>
<body>

<span id="top"></span>
<input type="checkbox" id="nav-toggle">
<label for="nav-toggle" id="nav-overlay"></label>

<div id="wrapper">
    <div id="header-placeholder"></div>
    <div id="main-layout">
        <div id="sidebar-placeholder"></div>

        <main id="content">
            <article class="blog-post">
                <div class="blog-post-header" style="flex-direction:column;align-items:flex-start;gap:8px;">
                    <span class="blog-post-title" style="font-size:10px;">${titleEn}</span>
                    <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;">
                        <span class="blog-post-date">${dateEn}</span>
                        <div class="post-tags">${tags.map(t => `<span class="post-tag">${t}</span>`).join('')}</div>
                    </div>
                </div>
                <div class="post-body">
                    ${thumbnail ? `<img src="${thumbnail}" class="post-hero-img" alt="${titleEn}">` : ''}
                    ${bodyHtml}
                </div>
            </article>
            <a href="/devlog.html" class="view-all" style="margin-top:20px;display:inline-block;">&laquo; BACK TO DEVLOG</a>
        </main>

    </div>
    <div id="footer-placeholder"></div>
</div>

<a href="#top" id="back-to-top" title="Back to top">&#9650;</a>

<script>
function loadComponent(id, file, cb) {
    fetch(file).then(r=>r.text()).then(html=>{
        document.getElementById(id).innerHTML=html;
        if(cb) cb();
    });
}
loadComponent('header-placeholder',  '/components/header.html');
loadComponent('sidebar-placeholder', '/components/sidebar.html');
loadComponent('footer-placeholder',  '/components/footer.html', function(){ initI18n(); });
</script>
<script src="/assets/i18n.js"></script>

</body>
</html>`;

        fs.writeFileSync(path.join('posts', `${slug}.html`), postHtml, 'utf8');
        console.log(`✅ Built posts/${slug}.html`);

        posts.push({ id: slug, date, date_en: dateEn, date_es: dateEs,
            title_en: titleEn, title_es: titleEs,
            excerpt_en: excerptEn, excerpt_es: excerptEs,
            thumbnail, tags });
    }

    // 4. Overwrite posts.json
    fs.writeFileSync('posts.json', JSON.stringify({ posts }, null, 2), 'utf8');
    console.log(`✅ posts.json updated with ${posts.length} posts`);
}

main().catch(err => { console.error(err); process.exit(1); });
