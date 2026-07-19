document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("simulation-form");
  const submitButton = document.getElementById("simulate-button");
  const progressMessage = document.getElementById("progress-message");
  const errorMessage = document.getElementById("error-message");

  window.PlasmonInputForm.initialize();
  window.PlasmonResults.initialize();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorMessage.hidden = true;
    submitButton.disabled = true;
    progressMessage.textContent = "計算しています。完了までお待ちください。";

    try {
      const payload = window.PlasmonInputForm.buildPayload();
      const result = await window.PlasmonApi.simulate(payload);
      window.PlasmonResults.renderResult(result);
      progressMessage.textContent = "計算が完了しました。";
    } catch (error) {
      errorMessage.textContent = error.message;
      errorMessage.hidden = false;
      progressMessage.textContent = "計算を開始できませんでした。";
    } finally {
      submitButton.disabled = false;
    }
  });
});
