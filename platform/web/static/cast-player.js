// 把页面里每个 [data-cast] 变成 asciinema 播放器。
// 单独成文件而不是写在 HTML 里：页面的 CSP 是 script-src 'self'，内联脚本进不来。
// 播放器本体在 asciinema-player/ 下，Apache-2.0，随仓库走，不引外站。
(function () {
  "use strict";
  if (typeof AsciinemaPlayer === "undefined") { return; }
  document.querySelectorAll("[data-cast]").forEach(function (el) {
    AsciinemaPlayer.create(el.dataset.cast, el, {
      fit: "width",
      idleTimeLimit: 3,          // 和录制参数一致：长停顿压到 3 秒
      terminalFontSize: "13px",
      terminalFontFamily: "Menlo, Consolas, 'DejaVu Sans Mono', monospace",
      theme: "asciinema",
      controls: true,
      speed: 1,
    });
  });
})();
