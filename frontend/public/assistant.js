"use strict";

(() => {
  const chat = { messages: [], busy: false, draft: "" };
  let mount = null;
  const arrow = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6"/></svg>';
  const spark = '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m16 3 3.7 9.3L29 16l-9.3 3.7L16 29l-3.7-9.3L3 16l9.3-3.7L16 3Z"/></svg>';
  const labels = { answered: "Данные получены", not_found: "Партия не найдена", insufficient_data: "Нужно уточнение", needs_clarification: "Уточните дату", out_of_scope: "Вне темы" };
  const format = value => new Intl.NumberFormat("ru-RU").format(value);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const current = () => mount?.isConnected && mount.querySelector("#assistant-chat");

  function messageView(message) {
    const article = el("article", `assistant-message ${message.role}`);
    article.append(el("div", "assistant-message-label", message.role === "user" ? "Вы" : "Ассистент"));
    const bubble = el("div", "assistant-bubble");
    if (message.error) bubble.classList.add("assistant-error");
    if (message.result) bubble.append(el("span", `assistant-status ${message.result.status}`, labels[message.result.status] || "Ответ"));
    bubble.append(el("p", "assistant-answer", message.text));
    const result = message.result;
    if (result?.status === "answered" && result.data) {
      const metrics = el("div", "assistant-metrics");
      for (const [label, field] of [["Всего изделий", "total"], ["Агрегировано", "aggregated"], ["Осталось", "remaining"]]) {
        const metric = el("div");
        metric.append(el("span", "", label), el("strong", "", format(result.data[field])));
        metrics.append(metric);
      }
      bubble.append(metrics);
      const sources = el("div", "assistant-sources");
      sources.append(el("span", "", `Партия · ID ${result.data.batch_id}`));
      sources.append(el("span", "", result.tools_called?.includes("get_batch_statistics") ? "Источник: сервис статистики" : "Статистика партии"));
      bubble.append(sources);
    }
    if (result?.search?.items?.length) {
      const found = el("div", "assistant-found-list");
      for (const batch of result.search.items) {
        const card = el("div", "assistant-found-card");
        card.append(el("strong", "", `Партия №${batch.batch_number}`));
        card.append(el("span", "", `ID ${batch.id} · ${batch.batch_date} · Цех ${batch.work_center_id} · ${batch.is_closed ? "Закрыта" : "В работе"}`));
        const details = el("button", "btn", `Статистика ID ${batch.id} ↗`);
        details.type = "button";
        details.addEventListener("click", () => selectQuestion(`Покажи статистику партии с ID ${batch.id}`));
        card.append(details);
        found.append(card);
      }
      bubble.append(found);
      bubble.append(el("div", "assistant-sources", `Источник: поиск партий · Всего найдено: ${result.search.total}`));
    }
    article.append(bubble);
    return article;
  }

  function update() {
    if (!current()) return;
    const list = mount.querySelector("#assistant-messages");
    list.replaceChildren(...chat.messages.map(messageView));
    mount.querySelector("#assistant-welcome").hidden = chat.messages.length > 0;
    list.hidden = chat.messages.length === 0;
    mount.querySelector("#assistant-pending").hidden = !chat.busy;
    mount.querySelector("#assistant-chat").setAttribute("aria-busy", String(chat.busy));
    const question = mount.querySelector("#assistant-question");
    mount.querySelector("#assistant-send").disabled = chat.busy || !question.value.trim();
    mount.querySelector("#assistant-clear").disabled = chat.busy || chat.messages.length === 0;
    question.disabled = chat.busy;
    mount.querySelector("#assistant-count").textContent = `${question.value.length} / 2000`;
  }

  function selectQuestion(text) {
    if (chat.busy || !current()) return;
    chat.draft = text;
    const input = mount.querySelector("#assistant-question");
    input.value = text;
    input.focus();
    update();
  }

  async function ask(event) {
    event.preventDefault();
    if (chat.busy) return;
    const input = mount.querySelector("#assistant-question");
    const question = input.value.trim();
    if (!question || question.length > 2000) return;
    chat.messages.push({ role: "user", text: question });
    chat.draft = "";
    input.value = "";
    chat.busy = true;
    update();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch("/api/v1/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) {
        const errors = {
          401: "Нет доступа к ассистенту. Проверьте настройки локального запуска API.",
          422: "Проверьте вопрос: от 1 до 2000 символов.",
          429: "Слишком много запросов. Попробуйте немного позже.",
          502: "API недоступен. Проверьте, что сервер приложения запущен.",
          503: "Ассистент недоступен. Проверьте настройки и подключение сервисов.",
          504: "Ассистент не успел ответить. Попробуйте ещё раз.",
        };
        const retry = response.headers.get("Retry-After");
        throw new Error((errors[response.status] || "Не удалось получить ответ.") + (response.status === 429 && /^\d+$/.test(retry || "") ? ` Повторите через ${retry} сек.` : ""));
      }
      if (!result || typeof result.answer !== "string" || !Object.hasOwn(labels, result.status)) throw new Error("Сервер вернул неожиданный ответ. Обновите приложение.");
      chat.messages.push({ role: "assistant", text: result.answer, result });
    } catch (error) {
      chat.messages.push({ role: "assistant", error: true, text: error.name === "AbortError" ? "Время ожидания истекло. Проверьте подключение и попробуйте ещё раз." : error instanceof TypeError ? "Не удалось связаться с сервером. Проверьте подключение." : error.message });
    } finally {
      clearTimeout(timeout);
      chat.busy = false;
      update();
      if (current()) {
        const last = mount.querySelector("#assistant-messages").lastElementChild;
        last?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        mount.querySelector("#assistant-question").focus();
      }
    }
  }

  window.renderAssistant = container => {
    mount = container;
    container.innerHTML = `
      <div class="page-heading"><div><p class="eyebrow">PRODUCTION CONTROL / AI</p><h1>Ассистент производства</h1><p class="subtitle">Поиск и статистика партий — простым вопросом</p></div><span class="assistant-readonly"><i></i>Только чтение</span></div>
      <div class="assistant-layout">
        <section class="assistant-main panel" id="assistant-chat" aria-label="Чат с ассистентом">
          <div class="assistant-chat-head"><span class="assistant-mini-spark">${spark}</span><div><h2>Помощник по партиям</h2><p>Ответы на основе производственных данных</p></div><button class="btn ghost" id="assistant-clear" type="button">Очистить</button></div>
          <div class="assistant-stage">
            <div class="assistant-welcome" id="assistant-welcome"><div class="assistant-orb">${spark}</div><p class="assistant-kicker">ОТ ВОПРОСА К ДАННЫМ</p><h2>Что происходит<br>с вашей партией?</h2><p>Укажите ID или номер партии. Ассистент найдёт её<br class="assistant-wide-break"> или покажет показатели.</p><div class="assistant-prompts"><button type="button" data-question="Сколько изделий осталось в партии с ID 1?">Остаток партии <span>↗</span></button><button type="button" data-question="Сколько всего изделий в партии с ID 1?">Количество изделий <span>↗</span></button><button type="button" data-question="Сколько изделий агрегировано в партии с ID 1?">Ход агрегации <span>↗</span></button></div></div>
            <div id="assistant-messages" class="assistant-messages" role="log" aria-live="polite" aria-label="Вопросы и ответы" hidden></div>
            <div id="assistant-pending" class="assistant-pending" role="status" hidden><span class="assistant-dots"><i></i><i></i><i></i></span>Получаем данные партии…</div>
          </div>
          <form id="assistant-form" class="assistant-composer"><label for="assistant-question" class="assistant-sr-only">Ваш вопрос</label><textarea id="assistant-question" rows="2" maxlength="2000" required placeholder="Например: сколько осталось изделий в партии с ID 1?"></textarea><div class="assistant-composer-bottom"><span>Enter — отправить · Shift + Enter — новая строка</span><span id="assistant-count">0 / 2000</span><button type="submit" id="assistant-send" aria-label="Отправить вопрос">${arrow}</button></div></form>
          <p class="assistant-context-note">Каждый вопрос самостоятельный. Указывайте ID или номер и дату партии в каждом сообщении.</p>
        </section>
        <aside class="assistant-aside"><section class="panel assistant-access"><div class="assistant-section-label">ВАШ ПОМОЩНИК</div><h2>Спросите о партии</h2><p>Ассистент сам получит статистику производства. Для поиска укажите номер и дату партии. Для статистики — внутренний ID.</p><p class="assistant-key-note">Доступны количество изделий, агрегация и остаток. Изменять данные ассистент не может.</p></section><section class="panel assistant-guide"><div class="assistant-section-label">КАК ЭТО РАБОТАЕТ</div><ol><li><span>01</span><div>Задайте вопрос<small>Поиск по номеру или статистика по ID</small></div></li><li><span>02</span><div>Получите статистику<small>Числа приходят из сервиса проекта</small></div></li><li><span>03</span><div>Проверьте результат<small>Всего, агрегировано и остаток</small></div></li></ol><a href="#batches">Открыть список партий <span>↗</span></a></section></aside>
      </div>`;
    const input = container.querySelector("#assistant-question");
    input.value = chat.draft;
    input.addEventListener("input", () => { chat.draft = input.value; update(); });
    input.addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); if (!container.querySelector("#assistant-send").disabled) container.querySelector("#assistant-form").requestSubmit(); }
    });
    container.querySelector("#assistant-form").addEventListener("submit", ask);
    container.querySelectorAll("[data-question]").forEach(button => button.addEventListener("click", () => selectQuestion(button.dataset.question)));
    container.querySelector("#assistant-clear").addEventListener("click", () => { chat.messages = []; update(); });
    update();
  };
})();
