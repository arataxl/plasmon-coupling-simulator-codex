document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("simulation-form");
  const submitButton = document.getElementById("simulate-button");
  const cancelButton = document.getElementById("cancel-button");
  const progressBar = document.getElementById("simulation-progress");
  const progressMessage = document.getElementById("progress-message");
  const errorMessage = document.getElementById("error-message");

  function setRunning(isRunning) {
    submitButton.disabled = isRunning;
    cancelButton.disabled = !isRunning;
  }

  function showError(error) {
    errorMessage.textContent = error.message;
    errorMessage.hidden = false;
  }

  window.PlasmonInputForm.initialize();
  window.PlasmonResults.initialize();
  setRunning(false);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorMessage.hidden = true;
    try {
      const payload = window.PlasmonInputForm.buildPayload();
      setRunning(true);
      progressBar.max = 1;
      progressBar.value = 0;
      progressMessage.textContent = "計算ジョブを開始しています。";
      await window.PlasmonProgress.start(payload, {
        onProgress(progress) {
          progressBar.max = progress.total_points;
          progressBar.value = progress.completed_points;
          progressMessage.textContent = `計算中: ${progress.completed_points} / ${progress.total_points} 波長点`;
        },
        onComplete(result) {
          progressBar.value = progressBar.max;
          window.PlasmonResults.renderResult(result);
          progressMessage.textContent = "計算が完了しました。";
          setRunning(false);
        },
        onCancelled() {
          progressMessage.textContent = "計算を取り消しました。部分結果は返却・保存していません。";
          setRunning(false);
        },
        onError(error) {
          showError(error);
          progressMessage.textContent = "計算を完了できませんでした。";
          setRunning(false);
        },
      });
    } catch (error) {
      showError(error);
      progressMessage.textContent = "計算を開始できませんでした。";
      setRunning(false);
    }
  });

  cancelButton.addEventListener("click", async () => {
    cancelButton.disabled = true;
    progressMessage.textContent = "取消を要求しました。現在の波長点が終わり次第、中断します。";
    try {
      const accepted = await window.PlasmonProgress.cancel();
      if (!accepted) {
        progressMessage.textContent = "計算はすでに完了しているため、取消できませんでした。";
      }
    } catch (error) {
      showError(error);
      if (window.PlasmonProgress.isActive()) {
        cancelButton.disabled = false;
      }
    }
  });
});
