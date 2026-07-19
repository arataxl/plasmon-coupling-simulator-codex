window.PlasmonApi = (() => {
  async function simulate(payload) {
    const response = await fetch("/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      const message = body.error?.message ?? "計算リクエストに失敗しました。";
      throw new Error(message);
    }
    return body;
  }

  return { simulate };
})();
