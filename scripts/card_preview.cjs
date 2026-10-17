/* Local, simulated card preview and browser-test server. */
const { createServer } = require("node:http");
const { readFile } = require("node:fs/promises");
const { join } = require("node:path");
const root = join(__dirname, "..");
const files = {
  "/": ["tests/frontend/preview.html", "text/html"],
  "/fixture.js": ["tests/frontend/fixture.js", "text/javascript"],
  "/card.js": ["custom_components/volcano_integration/www/volcano-hybrid-card.js", "text/javascript"],
};
function createPreviewServer() {
  return createServer(async (request, response) => {
    const file = files[new URL(request.url, "http://localhost").pathname];
    if (!file) { response.writeHead(404).end(); return; }
    try {
      const content = await readFile(join(root, file[0]));
      response.writeHead(200, { "Content-Type": `${file[1]}; charset=utf-8`, "Cache-Control": "no-store" }).end(content);
    } catch { response.writeHead(500).end(); }
  });
}
module.exports = { createPreviewServer };
if (require.main === module) createPreviewServer().listen(8765, "127.0.0.1", () => {
  console.log("Volcano simulated preview: http://127.0.0.1:8765");
});
