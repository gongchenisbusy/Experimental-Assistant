const stageDetails = [...document.querySelectorAll(".stage-details")];
const status = document.querySelector("#details-status");

function setAllDetails(open) {
  stageDetails.forEach((details) => {
    details.open = open;
  });
  if (status) {
    status.textContent = open ? "已展开全部阶段" : "已收起全部阶段";
  }
}

document.querySelector('[data-action="expand-all"]')?.addEventListener("click", () => {
  setAllDetails(true);
});

document.querySelector('[data-action="collapse-all"]')?.addEventListener("click", () => {
  setAllDetails(false);
});

document.querySelector(".report-details")?.addEventListener("toggle", (event) => {
  const details = event.currentTarget;
  const frame = details.querySelector("iframe[data-src]");
    if (details.open && frame && !frame.getAttribute("src")) {
      frame.src = frame.dataset.src;
    }
});
