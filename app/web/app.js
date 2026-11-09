/* PushAll 消息中心 · 前端逻辑（Vue 3，无需构建） */
const { createApp } = Vue;

const api = async (path, options = {}) => {
  const opts = { ...options, headers: { ...(options.headers || {}) } };
  if (!(opts.body instanceof FormData) && opts.body !== undefined && !opts.headers["Content-Type"]) {
    opts.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, opts);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = { detail: text }; }
  if (!res.ok) {
    const detail = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return data;
};

const clone = (obj) => JSON.parse(JSON.stringify(obj));

const SchemaForm = {
  props: {
    schema: { type: Object, default: () => ({}) },
    modelValue: { type: Object, default: () => ({}) }
  },
  emits: ["update:modelValue"],
  computed: {
    fields() {
      return Object.entries((this.schema && this.schema.properties) || {}).map(([key, spec]) => ({ key, ...spec }));
    },
    required() {
      return (this.schema && this.schema.required) || [];
    }
  },
  methods: {
    isRequired(key) { return this.required.includes(key); },
    widget(f) {
      const ui = f["x-ui"] || {};
      if (ui.widget) return ui.widget;
      if (f.enum) return "select";
      if (f.type === "boolean") return "switch";
      if (f.type === "integer" || f.type === "number") return "number";
      return "text";
    },
    val(key) {
      const v = this.modelValue ? this.modelValue[key] : undefined;
      return v === undefined || v === null ? "" : v;
    },
    set(key, value) {
      this.$emit("update:modelValue", { ...this.modelValue, [key]: value });
    },
    inputType(f) {
      const w = this.widget(f);
      if (w === "password") return "password";
      if (w === "number") return "number";
      return "text";
    },
    placeholder(f) { return (f["x-ui"] || {}).placeholder || ""; },
    isSwitch(f) { return this.widget(f) === "switch"; },
    isCode(f) { const w = this.widget(f); return w === "code" || w === "textarea"; }
  },
  template: `
    <div class="schema-form">
      <div class="field" v-for="f in fields" :key="f.key" :class="{ 'field-wide': isCode(f) }">
        <label v-if="!isSwitch(f)">{{ f.title || f.key }}<span class="req" v-if="isRequired(f.key)">*</span></label>

        <select v-if="widget(f) === 'select'" :value="val(f.key)" @change="set(f.key, $event.target.value)">
          <option v-for="opt in f.enum" :key="opt" :value="opt">{{ opt }}</option>
        </select>

        <textarea
          v-else-if="isCode(f)"
          class="code"
          :rows="(f['x-ui'] || {}).rows || 4"
          :value="val(f.key)"
          :placeholder="placeholder(f)"
          @input="set(f.key, $event.target.value)"></textarea>

        <label v-else-if="isSwitch(f)" class="switch-line">
          <span class="switch"><input type="checkbox" :checked="!!modelValue[f.key]" @change="set(f.key, $event.target.checked)"><i></i></span>
          <span>{{ f.title || f.key }}</span>
        </label>

        <input
          v-else
          :type="inputType(f)"
          :value="val(f.key)"
          :placeholder="placeholder(f)"
          @input="set(f.key, widget(f) === 'number' ? ($event.target.value === '' ? '' : Number($event.target.value)) : $event.target.value)">

        <div class="help" v-if="f.description">{{ f.description }}</div>
      </div>
    </div>`
};

const app = createApp({
  data() {
    return {
      view: "scenarios",
      loading: false,
      meta: {},
      plugins: [],
      sources: [],
      channels: [],
      templates: [],
      scenarios: [],
      runs: [],
      current: null,
      step: "basic",
      scenarioFilter: "",
      moreOpen: false,
      running: false,
      sourceTest: null,
      sourceTesting: false,
      nextRuns: [],
      runFilter: null,
      modal: null,
      previewResult: null,
      runDetail: null,
      updateInfo: null,
      updateChecking: false,
      updateProxy: { enabled: false, type: "http", host: "127.0.0.1", port: 1080, username: "", password: "", has_password: false },
      proxyTesting: false,
      proxyTest: null,
      maskMouseDown: false,
      toast: null,
      _toastTimer: null,
      navs: [
        { key: "scenarios", label: "消息场景", icon: "◈" },
        { key: "sources", label: "数据源", icon: "▤" },
        { key: "templates", label: "模板", icon: "✎" },
        { key: "channels", label: "渠道", icon: "➤" },
        { key: "plugins", label: "插件", icon: "⬡" },
        { key: "runs", label: "运行记录", icon: "◷" },
        { key: "settings", label: "设置", icon: "⚙" }
      ],
      stepTabs: [
        { key: "basic", label: "基本" },
        { key: "source", label: "数据源" },
        { key: "template", label: "模板" },
        { key: "push", label: "推送" },
        { key: "schedule", label: "调度" }
      ],
      scheduleModes: [
        { value: "manual", label: "手动", desc: "只在你点击时运行" },
        { value: "cron", label: "定时", desc: "按 cron 周期自动运行" },
        { value: "webhook", label: "外部调用", desc: "由其他系统 POST 触发" }
      ],
      cronPresets: [
        { label: "每天 09:00", expr: "0 9 * * *" },
        { label: "每小时", expr: "0 * * * *" },
        { label: "工作日 18:00", expr: "0 18 * * 1-5" },
        { label: "每周一 09:00", expr: "0 9 * * 1" },
        { label: "每月 1 号 09:00", expr: "0 9 1 * *" }
      ]
    };
  },

  computed: {
    pageTitle() {
      const map = {
        scenarios: "消息场景",
        sources: "数据源",
        templates: "模板",
        channels: "渠道",
        plugins: "插件",
        runs: "运行记录",
        settings: "设置"
      };
      return map[this.view] || "PushAll";
    },
    pageSubtitle() {
      const map = {
        scenarios: "取数 → 模板 → 推送，一个场景就是一条完整链路",
        sources: "可复用的数据库连接与接口配置",
        templates: "消息标题与 Markdown 正文",
        channels: "钉钉群机器人与邮箱",
        plugins: "扩展数据来源和下游系统",
        runs: "每次执行的全链路结果",
        settings: "运行信息与配置备份"
      };
      return map[this.view] || "";
    },
    filteredScenarios() {
      const q = this.scenarioFilter.trim().toLowerCase();
      if (!q) return this.scenarios;
      return this.scenarios.filter((s) => (s.name + " " + (s.description || "")).toLowerCase().includes(q));
    },
    failedCount() {
      return this.runs.filter((r) => r.status === "failed").length;
    },
    hookUrl() {
      return this.current && this.current.id ? `${location.origin}/api/hooks/${this.current.id}` : "";
    },
    modalPlugin() {
      if (!this.modal || !this.modal.item) return null;
      return this.plugins.find((p) => p.id === this.modal.item.plugin_id) || null;
    }
  },

  methods: {
    /* ---------- 基础 ---------- */
    async refreshAll() {
      this.loading = true;
      try {
        const [meta, plugins, sources, channels, templates, scenarios] = await Promise.all([
          api("/api/meta"), api("/api/plugins"), api("/api/sources"),
          api("/api/channels"), api("/api/templates"), api("/api/scenarios")
        ]);
        this.meta = meta;
        this.plugins = plugins;
        this.sources = sources;
        this.channels = channels;
        this.templates = templates;
        this.scenarios = scenarios;
        if (this.current && this.current.id) {
          const fresh = scenarios.find((s) => s.id === this.current.id);
          if (fresh) this.current = clone(fresh);
        }
      } catch (e) {
        this.toastMsg("加载失败：" + e.message, "bad");
      } finally {
        this.loading = false;
      }
    },

    go(view) {
      this.view = view;
      this.moreOpen = false;
      if (view === "runs") this.loadRuns();
      if (view === "settings") this.loadUpdateProxy();
    },

    toastMsg(text, type = "ok") {
      this.toast = { text, type };
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => { this.toast = null; }, 3200);
    },

    pluginName(id) {
      const p = this.plugins.find((x) => x.id === id);
      return p ? p.name : id || "未知插件";
    },
    pluginIcon(icon) {
      const map = { database: "▤", globe: "◍", file: "▦", dingtalk: "✆", mail: "✉", webhook: "⇢" };
      return map[icon] || "⬡";
    },
    pluginsByType(type) {
      return this.plugins.filter((p) => p.type === type && !p.error);
    },
    statusClass(status) {
      return { success: "success", failed: "failed", partial: "warning", skipped: "muted", busy: "blue" }[status] || "muted";
    },
    statusText(status) {
      return { success: "成功", failed: "失败", partial: "部分成功", skipped: "已跳过", busy: "运行中" }[status] || "未运行";
    },
    triggerText(trigger) {
      return { manual: "手动", cron: "定时", webhook: "外部", preview: "预览" }[trigger] || trigger;
    },
    scheduleText(s) {
      if (s.schedule_mode === "cron") return "cron " + s.cron;
      if (s.schedule_mode === "webhook") return "外部调用";
      return "手动";
    },
    pretty(obj) {
      try { return typeof obj === "string" ? obj : JSON.stringify(obj, null, 2); } catch (e) { return String(obj); }
    },
    prettyDetail(detail) {
      try { return JSON.stringify(JSON.parse(detail || "{}"), null, 2); } catch (e) { return detail || ""; }
    },
    closeModal() { this.modal = null; this.previewResult = null; this.runDetail = null; },

    scheduleMaskReset() {
      // mouseup 先于 click；延迟重置，保证 click.self 仍能读到本次的按下状态
      setTimeout(() => { this.maskMouseDown = false; }, 0);
    },

    onMaskClick() {
      if (!this.maskMouseDown) return;
      this.maskMouseDown = false;
      this.closeModal();
    },
    ask(title, message, onOk) {
      this.modal = { type: "confirm", title, message, onOk };
    },
    copyText(text) {
      navigator.clipboard.writeText(text).then(
        () => this.toastMsg("已复制"),
        () => this.toastMsg("复制失败，请手动复制", "bad")
      );
    },

    /* ---------- 场景 ---------- */
    newScenario() {
      this.current = {
        id: null,
        name: "新场景",
        description: "",
        enabled: true,
        source_id: null,
        template_id: null,
        channel_ids: [],
        schedule_mode: "manual",
        cron: "0 9 * * *",
        options: { send_when_empty: false, retry: 1 },
        last_run_at: "",
        last_status: ""
      };
      this.step = "basic";
      this.sourceTest = null;
      this.nextRuns = [];
      this.moreOpen = false;
    },

    selectScenario(id, keepStep = false) {
      const found = this.scenarios.find((s) => s.id === id);
      if (!found) return;
      this.current = clone(found);
      if (!this.current.options) this.current.options = { send_when_empty: false, retry: 1 };
      if (!this.current.channel_ids) this.current.channel_ids = [];
      if (!keepStep) this.step = "basic";
      this.sourceTest = null;
      this.nextRuns = [];
      this.moreOpen = false;
    },

    scenarioPayload() {
      return {
        name: (this.current.name || "").trim(),
        description: this.current.description || "",
        enabled: !!this.current.enabled,
        source_id: this.current.source_id || null,
        template_id: this.current.template_id || null,
        channel_ids: this.current.channel_ids || [],
        schedule_mode: this.current.schedule_mode || "manual",
        cron: this.current.cron || "",
        options: this.current.options || {}
      };
    },

    async saveScenario() {
      if (!this.current) return;
      if (!(this.current.name || "").trim()) return this.toastMsg("请填写场景名称", "bad");
      try {
        const payload = this.scenarioPayload();
        const saved = this.current.id
          ? await api(`/api/scenarios/${this.current.id}`, { method: "PUT", body: JSON.stringify(payload) })
          : await api("/api/scenarios", { method: "POST", body: JSON.stringify(payload) });
        await this.refreshAll();
        this.selectScenario(saved.id, true);
        this.toastMsg("场景已保存");
      } catch (e) {
        this.toastMsg("保存失败：" + e.message, "bad");
      }
    },

    async previewScenario() {
      if (!this.current || !this.current.id) return this.toastMsg("请先保存场景", "bad");
      try {
        this.previewResult = await api(`/api/scenarios/${this.current.id}/preview`, { method: "POST", body: "{}" });
        this.modal = { type: "preview" };
      } catch (e) {
        this.toastMsg("预览失败：" + e.message, "bad");
      }
    },

    async runScenario() {
      if (!this.current || !this.current.id) return this.toastMsg("请先保存场景", "bad");
      await this.runScenarioById(this.current.id);
    },

    async runScenarioById(id) {
      this.running = true;
      try {
        const res = await api(`/api/scenarios/${id}/run`, { method: "POST" });
        await this.refreshAll();
        await this.loadRuns();
        if (res.status === "success" || res.status === "skipped") {
          this.toastMsg(res.message || "执行完成");
        } else {
          this.toastMsg(res.message || "执行失败", "bad");
          if (res.run_id) await this.openRun(res.run_id);
        }
      } catch (e) {
        this.toastMsg("执行失败：" + e.message, "bad");
      } finally {
        this.running = false;
      }
    },

    duplicateScenario() {
      if (!this.current || !this.current.id) return;
      this.ask("复制场景", `确定复制「${this.current.name}」吗？副本默认停用。`, async () => {
        try {
          const created = await api(`/api/scenarios/${this.current.id}/duplicate`, { method: "POST" });
          await this.refreshAll();
          this.selectScenario(created.id);
          this.toastMsg("已复制");
        } catch (e) { this.toastMsg("复制失败：" + e.message, "bad"); }
      });
    },

    removeScenario() {
      if (!this.current || !this.current.id) return;
      const id = this.current.id;
      this.ask("删除场景", `确定删除「${this.current.name}」？运行记录也会一并删除。`, async () => {
        try {
          await api(`/api/scenarios/${id}`, { method: "DELETE" });
          this.current = null;
          await this.refreshAll();
          this.toastMsg("已删除");
        } catch (e) { this.toastMsg("删除失败：" + e.message, "bad"); }
      });
    },

    async testCurrentSource() {
      const src = this.sources.find((s) => s.id === this.current.source_id);
      if (!src) return;
      this.sourceTesting = true;
      this.sourceTest = null;
      try {
        this.sourceTest = await api("/api/sources/test", {
          method: "POST",
          body: JSON.stringify({ plugin_id: src.plugin_id, config: src.config })
        });
      } catch (e) {
        this.sourceTest = { ok: false, message: e.message, rows: [] };
      } finally {
        this.sourceTesting = false;
      }
    },

    async checkCron() {
      try {
        const res = await api("/api/cron/next?expr=" + encodeURIComponent(this.current.cron || ""));
        this.nextRuns = res.next || [];
      } catch (e) {
        this.nextRuns = [];
        this.toastMsg("cron 不合法：" + e.message, "bad");
      }
    },

    /* ---------- 数据源 / 渠道 ---------- */
    openConfigModal(kind, item = null) {
      const type = kind === "source" ? "source" : "sink";
      const list = this.pluginsByType(type);
      const base = item ? clone(item) : { id: null, name: "", plugin_id: (list[0] || {}).id || "", config: {} };
      if (!item && list[0]) base.config = this.defaultConfig(list[0]);
      this.modal = { type: kind, item: base, test: null, testing: false };
    },

    defaultConfig(plugin) {
      const cfg = {};
      const props = (plugin && plugin.schema && plugin.schema.properties) || {};
      Object.entries(props).forEach(([key, spec]) => {
        if (spec.default !== undefined) cfg[key] = spec.default;
        else if (spec.type === "boolean") cfg[key] = false;
        else cfg[key] = "";
      });
      return cfg;
    },

    onModalPluginChange() {
      const p = this.modalPlugin;
      this.modal.item.config = p ? this.defaultConfig(p) : {};
      this.modal.test = null;
    },

    async testModal() {
      if (!this.modal || !this.modal.item) return;
      const isSource = this.modal.type === "source";
      this.modal.testing = true;
      try {
        const res = await api(isSource ? "/api/sources/test" : "/api/channels/test", {
          method: "POST",
          body: JSON.stringify({ plugin_id: this.modal.item.plugin_id, config: this.modal.item.config })
        });
        this.modal.test = res;
      } catch (e) {
        this.modal.test = { ok: false, message: e.message, rows: [] };
      } finally {
        this.modal.testing = false;
      }
    },

    async quickTest(kind, item) {
      this.openConfigModal(kind, item);
      await this.testModal();
    },

    async saveModal() {
      const m = this.modal;
      if (!m || !m.item) return;
      if (!(m.item.name || "").trim()) return this.toastMsg("请填写名称", "bad");
      if (!m.item.plugin_id) return this.toastMsg("请选择插件", "bad");
      const isSource = m.type === "source";
      const body = { name: m.item.name.trim(), plugin_id: m.item.plugin_id, config: m.item.config || {} };
      try {
        if (m.item.id) {
          await api((isSource ? "/api/sources/" : "/api/channels/") + m.item.id, { method: "PUT", body: JSON.stringify(body) });
        } else {
          await api(isSource ? "/api/sources" : "/api/channels", { method: "POST", body: JSON.stringify(body) });
        }
        this.modal = null;
        await this.refreshAll();
        this.toastMsg("已保存");
      } catch (e) {
        this.toastMsg("保存失败：" + e.message, "bad");
      }
    },

    removeConfig(kind, item) {
      const isSource = kind === "source";
      this.ask("删除确认", `确定删除「${item.name}」？`, async () => {
        try {
          await api((isSource ? "/api/sources/" : "/api/channels/") + item.id, { method: "DELETE" });
          await this.refreshAll();
          this.toastMsg("已删除");
        } catch (e) { this.toastMsg("删除失败：" + e.message, "bad"); }
      });
    },

    /* ---------- 模板 ---------- */
    openTemplate(id) {
      const found = id ? this.templates.find((t) => t.id === id) : null;
      this.modal = {
        type: "template",
        item: found ? clone(found) : {
          id: null,
          name: "新模板",
          title_tpl: "{{ scenario.name }}（{{ count }} 条）",
          body_tpl: "### {{ scenario.name }}\n> {{ run.started_at }} · 共 {{ count }} 条\n\n{{ rows | md_table }}"
        },
        sample: JSON.stringify([
          { "店铺": "BJ001", "库存": 3, "安全库存": 10 },
          { "店铺": "BJ002", "库存": 7, "安全库存": 12 }
        ], null, 2),
        preview: null
      };
    },

    async previewTemplate() {
      try {
        const rows = JSON.parse(this.modal.sample || "[]");
        this.modal.preview = await api("/api/templates/preview", {
          method: "POST",
          body: JSON.stringify({
            title_tpl: this.modal.item.title_tpl,
            body_tpl: this.modal.item.body_tpl,
            rows
          })
        });
      } catch (e) {
        this.toastMsg("预览失败：" + e.message, "bad");
      }
    },

    async saveTemplate() {
      const m = this.modal;
      if (!m || !m.item || !(m.item.name || "").trim()) return this.toastMsg("请填写模板名称", "bad");
      const body = { name: m.item.name.trim(), title_tpl: m.item.title_tpl || "", body_tpl: m.item.body_tpl || "" };
      try {
        if (m.item.id) await api(`/api/templates/${m.item.id}`, { method: "PUT", body: JSON.stringify(body) });
        else await api("/api/templates", { method: "POST", body: JSON.stringify(body) });
        this.modal = null;
        await this.refreshAll();
        this.toastMsg("模板已保存");
      } catch (e) {
        this.toastMsg("保存失败：" + e.message, "bad");
      }
    },

    removeTemplate(t) {
      this.ask("删除模板", `确定删除「${t.name}」？`, async () => {
        try {
          await api(`/api/templates/${t.id}`, { method: "DELETE" });
          await this.refreshAll();
          this.toastMsg("已删除");
        } catch (e) { this.toastMsg("删除失败：" + e.message, "bad"); }
      });
    },

    /* ---------- 运行记录 ---------- */
    async loadRuns() {
      try {
        const q = this.runFilter ? `?scenario_id=${this.runFilter}&limit=100` : "?limit=100";
        this.runs = await api("/api/runs" + q);
      } catch (e) {
        this.toastMsg("加载运行记录失败：" + e.message, "bad");
      }
    },

    async openRun(id) {
      try {
        this.runDetail = await api(`/api/runs/${id}`);
        this.modal = { type: "run" };
      } catch (e) {
        this.toastMsg("加载详情失败：" + e.message, "bad");
      }
    },

    async rerun() {
      if (!this.runDetail) return;
      const scenarioId = this.runDetail.scenario_id;
      this.modal = null;
      await this.runScenarioById(scenarioId);
    },

    /* ---------- 插件 ---------- */
    pickPluginZip() { this.$refs.zipInput.click(); },

    async installPlugin(event) {
      const file = event.target.files[0];
      if (!file) return;
      const form = new FormData();
      form.append("file", file);
      try {
        await api("/api/plugins/install", { method: "POST", body: form });
        await this.refreshAll();
        this.toastMsg("插件已安装");
      } catch (e) {
        this.toastMsg("安装失败：" + e.message, "bad");
      } finally {
        event.target.value = "";
      }
    },

    async togglePlugin(p, enabled) {
      try {
        await api(`/api/plugins/${p.id}/enabled`, { method: "POST", body: JSON.stringify({ enabled }) });
        await this.refreshAll();
        this.toastMsg(enabled ? "插件已启用" : "插件已禁用");
      } catch (e) {
        this.toastMsg("操作失败：" + e.message, "bad");
      }
    },

    uninstallPlugin(p) {
      this.ask("卸载插件", `确定卸载「${p.name}」？插件目录会被删除。`, async () => {
        try {
          await api(`/api/plugins/${p.id}`, { method: "DELETE" });
          await this.refreshAll();
          this.toastMsg("插件已卸载");
        } catch (e) { this.toastMsg("卸载失败：" + e.message, "bad"); }
      });
    },

    /* ---------- 设置 ---------- */
    async exportData() {
      try {
        const data = await api("/api/export");
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `pushall-backup-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
      } catch (e) {
        this.toastMsg("导出失败：" + e.message, "bad");
      }
    },

    pickImport() { this.$refs.importInput.click(); },

    async checkUpdate() {
      this.updateChecking = true;
      try {
        this.updateInfo = await api("/api/update/check");
      } catch (e) {
        this.updateInfo = { ok: false, error: e.message };
      } finally {
        this.updateChecking = false;
      }
    },

    async loadUpdateProxy() {
      try {
        this.updateProxy = await api("/api/settings/update-proxy");
      } catch (e) {
        // 保持默认值
      }
    },

    async saveUpdateProxy() {
      try {
        const payload = { ...this.updateProxy };
        delete payload.has_password;
        this.updateProxy = await api("/api/settings/update-proxy", { method: "PUT", body: JSON.stringify(payload) });
        this.proxyTest = null;
        this.toastMsg("更新代理已保存");
      } catch (e) {
        this.toastMsg("保存失败：" + e.message, "bad");
      }
    },

    async testUpdateProxy() {
      this.proxyTesting = true;
      this.proxyTest = null;
      try {
        const payload = { ...this.updateProxy };
        delete payload.has_password;
        this.proxyTest = await api("/api/settings/update-proxy/test", { method: "POST", body: JSON.stringify(payload) });
      } catch (e) {
        this.proxyTest = { ok: false, message: e.message };
      } finally {
        this.proxyTesting = false;
      }
    },

    async installUpdate() {
      try {
        await api("/api/update/install", { method: "POST" });
        this.toastMsg("已开始下载更新，请留意桌面弹窗");
      } catch (e) {
        this.toastMsg("启动更新失败：" + e.message, "bad");
      }
    },

    async importData(event) {
      const file = event.target.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const res = await api("/api/import", { method: "POST", body: JSON.stringify(data) });
        await this.refreshAll();
        this.toastMsg(`导入完成：${res.scenarios} 个场景`);
      } catch (e) {
        this.toastMsg("导入失败：" + e.message, "bad");
      } finally {
        event.target.value = "";
      }
    }
  },

  mounted() {
    this.refreshAll();
    this.loadUpdateProxy();
  }
});

app.component("schema-form", SchemaForm);
app.mount("#app");



