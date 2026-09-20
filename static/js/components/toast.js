/**
 * Toast notification component
 */

export function showToast(message, type = "info") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  const bgClass =
    type === "success"
      ? "bg-emerald-900/90 border-emerald-500 text-emerald-100"
      : type === "error"
      ? "bg-rose-900/90 border-rose-500 text-rose-100"
      : "bg-slate-900/90 border-indigo-500 text-slate-100";

  toast.className = `pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-xl border shadow-xl backdrop-blur-md text-xs font-semibold transform transition-all duration-300 translate-y-4 opacity-0 ${bgClass}`;
  
  const icon =
    type === "success"
      ? '<i class="fa-solid fa-circle-check text-emerald-400"></i>'
      : type === "error"
      ? '<i class="fa-solid fa-triangle-exclamation text-rose-400"></i>'
      : '<i class="fa-solid fa-circle-info text-indigo-400"></i>';

  toast.innerHTML = `${icon}<span>${message}</span>`;
  container.appendChild(toast);

  // Animate in
  setTimeout(() => {
    toast.classList.remove("translate-y-4", "opacity-0");
  }, 10);

  // Auto remove
  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-2");
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
