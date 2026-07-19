document.addEventListener("DOMContentLoaded", async () => {
  await window.PlasmonI18n.initialize();

  const form = document.getElementById("simulation-form");
  const submitButton = document.getElementById("simulate-button");
  const cancelButton = document.getElementById("cancel-button");
  const progressBar = document.getElementById("simulation-progress");
  const progressMessage = document.getElementById("progress-message");
  const errorMessage = document.getElementById("error-message");
  const t = (key, parameters) => window.PlasmonI18n.t(key, parameters);

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
      progressMessage.textContent = t("progress.starting");
      await window.PlasmonProgress.start(payload, {
        onProgress(progress) {
          progressBar.max = progress.total_points;
          progressBar.value = progress.completed_points;
          progressMessage.textContent = t("progress.running", {
            completedPoints: progress.completed_points,
            totalPoints: progress.total_points,
          });
        },
        onComplete(result) {
          progressBar.value = progressBar.max;
          window.PlasmonResults.renderResult(result);
          progressMessage.textContent = t("progress.complete");
          setRunning(false);
        },
        onCancelled() {
          progressMessage.textContent = t("progress.cancelled");
          setRunning(false);
        },
        onError(error) {
          showError(error);
          progressMessage.textContent = t("progress.failed");
          setRunning(false);
        },
      });
    } catch (error) {
      showError(error);
      progressMessage.textContent = t("progress.startFailed");
      setRunning(false);
    }
  });

  cancelButton.addEventListener("click", async () => {
    cancelButton.disabled = true;
    progressMessage.textContent = t("progress.cancelling");
    try {
      const accepted = await window.PlasmonProgress.cancel();
      if (!accepted) {
        progressMessage.textContent = t("progress.alreadyComplete");
      }
    } catch (error) {
      showError(error);
      if (window.PlasmonProgress.isActive()) {
        cancelButton.disabled = false;
      }
    }
  });
});
