// 撮影まわり：カウントダウン、フラッシュ、撮影結果の表示と保存

export async function countdown(el, seconds) {
  if (!seconds) return;
  el.hidden = false;
  for (let i = seconds; i > 0; i--) {
    el.textContent = i;
    await new Promise((r) => setTimeout(r, 900));
  }
  el.hidden = true;
}

export function flash(el) {
  el.classList.remove('on');
  void el.offsetWidth;
  el.classList.add('on');
}

// 撮影結果：共有（iPhone/Androidの写真に保存）とダウンロードに対応
// 「もう一度 とる」で閉じると Promise が解決する
export function showResult(modal, canvas) {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      const file = new File([blob], `tsubamei-${timestamp()}.jpg`, { type: 'image/jpeg' });
      modal.querySelector('img').src = url;
      modal.hidden = false;

      const shareBtn = modal.querySelector('[data-act="share"]');
      const dlBtn = modal.querySelector('[data-act="download"]');
      const closeBtn = modal.querySelector('[data-act="close"]');
      const canShare = !!(navigator.canShare && navigator.canShare({ files: [file] }));
      shareBtn.hidden = !canShare;
      dlBtn.hidden = canShare; // 共有できる端末では「しゃしんを ほぞん」だけにする

      shareBtn.onclick = async () => {
        try { await navigator.share({ files: [file] }); } catch { /* キャンセル */ }
      };
      dlBtn.onclick = () => {
        const a = document.createElement('a');
        a.href = url;
        a.download = file.name;
        a.click();
      };
      closeBtn.onclick = () => {
        modal.hidden = true;
        URL.revokeObjectURL(url);
        shareBtn.onclick = dlBtn.onclick = closeBtn.onclick = null;
        resolve();
      };
    }, 'image/jpeg', 0.92);
  });
}

function timestamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}
