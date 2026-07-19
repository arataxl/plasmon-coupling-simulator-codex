document.addEventListener("DOMContentLoaded", async () => {
  await window.PlasmonI18n.initialize();

  const form = document.getElementById("simulation-form");
  const submitButton = document.getElementById("simulate-button");
  const cancelButton = document.getElementById("cancel-button");
  const progressBar = document.getElementById("simulation-progress");
  const progressMessage = document.getElementById("progress-message");
  const errorMessage = document.getElementById("error-message");
  const t = (key, parameters) => window.PlasmonI18n.t(key, parameters);
  let currentError = null;
  let progressStatus = null;

  function setRunning(isRunning) {
    submitButton.disabled = isRunning;
    cancelButton.disabled = !isRunning;
  }

  function showError(error) {
    currentError = error;
    errorMessage.textContent = window.PlasmonI18n.errorMessage(error);
    errorMessage.hidden = false;
  }

  function clearError() {
    currentError = null;
    errorMessage.textContent = "";
    errorMessage.hidden = true;
  }

  function setProgress(key, parameters = {}) {
    progressStatus = { key, parameters };
    progressMessage.textContent = t(key, parameters);
  }

  window.PlasmonInputForm.initialize();
  window.PlasmonResults.initialize();
  setRunning(false);
  window.addEventListener("plasmonlanguagechange", () => {
    if (currentError) {
      errorMessage.textContent = window.PlasmonI18n.errorMessage(currentError);
    }
    if (progressStatus) {
      progressMessage.textContent = t(progressStatus.key, progressStatus.parameters);
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    try {
      const payload = window.PlasmonInputForm.buildPayload();
      setRunning(true);
      progressBar.max = 1;
      progressBar.value = 0;
      setProgress("progress.starting");
      await window.PlasmonProgress.start(payload, {
        onProgress(progress) {
          progressBar.max = progress.total_points;
          progressBar.value = progress.completed_points;
          setProgress("progress.running", {
            completedPoints: progress.completed_points,
            totalPoints: progress.total_points,
          });
        },
        onComplete(result) {
          progressBar.value = progressBar.max;
          window.PlasmonResults.renderResult(result);
          setProgress("progress.complete");
          setRunning(false);
        },
        onCancelled() {
          setProgress("progress.cancelled");
          setRunning(false);
        },
        onError(error) {
          showError(error);
          setProgress("progress.failed");
          setRunning(false);
        },
      });
    } catch (error) {
      showError(error);
      setProgress("progress.startFailed");
      setRunning(false);
    }
  });

  cancelButton.addEventListener("click", async () => {
    cancelButton.disabled = true;
    setProgress("progress.cancelling");
    try {
      const accepted = await window.PlasmonProgress.cancel();
      if (!accepted) {
        setProgress("progress.alreadyComplete");
      }
    } catch (error) {
      showError(error);
      if (window.PlasmonProgress.isActive()) {
        cancelButton.disabled = false;
      }
    }
  });
});
