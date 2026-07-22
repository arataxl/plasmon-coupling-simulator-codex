window.PlasmonI18n = (() => {
  const defaultLanguage = "ja";
  const languageStorageKey = "plasmon-coupling-simulator.language.v1";
  const supportedLanguages = new Set(["ja", "en"]);
  let currentLanguage = defaultLanguage;
  let messages = null;

  function interpolate(template, parameters = {}) {
    return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key) => String(parameters[key] ?? `{${key}}`));
  }

  function t(key, parameters = {}) {
    if (!messages || typeof messages[key] !== "string") {
      return key;
    }
    return interpolate(messages[key], parameters);
  }

  function createLocalizedError(key, parameters = {}) {
    const error = new Error(t(key, parameters));
    error.translationKey = key;
    error.translationParameters = parameters;
    return error;
  }

  function errorMessage(error) {
    if (error?.translationKey) {
      return t(error.translationKey, error.translationParameters);
    }
    if (Array.isArray(error?.translationDescriptors)) {
      return error.translationDescriptors
        .map((descriptor) => t(descriptor.key, descriptor.parameters))
        .join(" ");
    }
    return error instanceof Error ? error.message : t("api.unknownError");
  }

  function applyTranslations(root = document) {
    if (!messages) {
      return;
    }
    root.querySelectorAll("[data-i18n]").forEach((element) => {
      element.textContent = t(element.dataset.i18n);
    });
    root.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
      element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
    });
    root.querySelectorAll("[data-i18n-tooltip]").forEach((element) => {
      const tooltip = t(element.dataset.i18nTooltip);
      element.dataset.tooltip = tooltip;
      element.setAttribute("aria-label", tooltip);
    });
    document.documentElement.lang = currentLanguage;
    document.querySelectorAll("[data-language]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.language === currentLanguage));
    });
  }

  async function loadLanguage(language) {
    const response = await fetch(`/static/js/i18n/${language}.json`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Could not load UI language: ${language}`);
    }
    const loadedMessages = await response.json();
    if (!loadedMessages || typeof loadedMessages !== "object") {
      throw new Error(`Invalid UI language file: ${language}`);
    }
    return loadedMessages;
  }

  function rememberedLanguage() {
    try {
      const language = window.localStorage.getItem(languageStorageKey);
      return supportedLanguages.has(language) ? language : defaultLanguage;
    } catch (_error) {
      return defaultLanguage;
    }
  }

  function rememberLanguage(language) {
    try {
      window.localStorage.setItem(languageStorageKey, language);
    } catch (_error) {
      // localStorage may be unavailable in privacy-restricted browser contexts.
    }
  }

  async function setLanguage(language, { remember = true } = {}) {
    const nextLanguage = supportedLanguages.has(language) ? language : defaultLanguage;
    try {
      messages = await loadLanguage(nextLanguage);
      currentLanguage = nextLanguage;
    } catch (error) {
      if (nextLanguage !== defaultLanguage) {
        messages = await loadLanguage(defaultLanguage);
        currentLanguage = defaultLanguage;
      } else {
        throw error;
      }
    }
    if (remember) {
      rememberLanguage(currentLanguage);
    }
    applyTranslations();
    window.dispatchEvent(new CustomEvent("plasmonlanguagechange", { detail: { language: currentLanguage } }));
  }

  async function initialize() {
    try {
      await setLanguage(rememberedLanguage(), { remember: false });
    } finally {
      // 保存済みの言語を読み終えるまで静的な日本語HTMLを見せないことで、
      // 英語を選択済みの利用者に日本語→英語のちらつきを見せない。
      document.documentElement.dataset.uiReady = "true";
    }
    document.querySelectorAll("[data-language]").forEach((button) => {
      button.addEventListener("click", () => {
        setLanguage(button.dataset.language).catch(() => {
          // 初期HTMLを残し、言語切替失敗を計算機能へ波及させない。
        });
      });
    });
  }

  return {
    applyTranslations,
    createLocalizedError,
    errorMessage,
    getLanguage: () => currentLanguage,
    initialize,
    setLanguage,
    t,
  };
})();
