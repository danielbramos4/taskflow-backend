"use strict";

const $ = (id) => document.getElementById(id);
const workspace = $("workspace");
const csrf = $("logout-form").querySelector("input[name=csrfmiddlewaretoken]").value;
const api = "/api/v1/organizations/";
const states = { todo: "A fazer", in_progress: "Em andamento", done: "Concluída" };
const state = { orgs: [], projects: [], members: [], org: null, project: null, page: 1, filter: {}, orgLoad: 0, taskLoad: 0 };
const orgPath = () => `${api}${state.org.id}/`;
const projectPath = () => `${orgPath()}projects/${state.project.id}/`;
const tasksPath = () => `${projectPath()}tasks/`;
const isOwner = () => state.org?.my_role === "owner";

function element(tag, content, className) {
    const node = document.createElement(tag);
    if (content != null) node.textContent = content;
    if (className) node.className = className;
    return node;
}

function notice(message = "", error = false) {
    const node = $("notice");
    node.textContent = message;
    node.classList.toggle("error", error);
    node.hidden = !message;
}

function errorText(body) {
    if (typeof body?.detail === "string") return body.detail;
    return Object.values(body || {}).flat().filter((item) => typeof item === "string").join(" ");
}

async function request(path, method = "GET", data) {
    const url = new URL(path, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith(api)) throw new Error("Endereço da API inválido.");
    const headers = { Accept: "application/json" };
    if (data !== undefined) Object.assign(headers, { "Content-Type": "application/json", "X-CSRFToken": csrf });
    const response = await fetch(url, {
        method, headers, credentials: "same-origin", redirect: "error",
        body: data === undefined ? undefined : JSON.stringify(data),
    });
    if (response.status === 401) {
        location.assign(workspace.dataset.login);
        throw new Error("Entre novamente para continuar.");
    }
    if (response.status === 204) return null;
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(response.status === 403 ? "Você não tem permissão para essa ação." : errorText(body) || "Não foi possível concluir a ação.");
    if (!body) throw new Error("A API não retornou os dados esperados.");
    return body;
}

async function allPages(path) {
    const results = [];
    while (path) {
        const response = await request(path);
        results.push(...response.results);
        path = response.next;
    }
    return results;
}

function options(select, values, selected = "") {
    select.replaceChildren(...values.map(([value, label]) => {
        const option = element("option", label);
        option.value = value;
        return option;
    }));
    select.value = String(selected);
}

function renderContext() {
    $("top-org").textContent = state.org?.name || "Projetos";
    $("project-title").textContent = state.project?.name || (state.org ? "Projetos da organização" : "Seus projetos");
    $("project-description").textContent = state.project?.description || (state.project?.is_archived ? "Projeto arquivado" : state.project ? "Acompanhe o trabalho e os próximos prazos da equipe." : "Selecione um projeto para acompanhar as tarefas.");
    $("add-project").hidden = !isOwner();
    $("add-member").hidden = !isOwner();
    $("new-task").hidden = !state.project || !isOwner();
    $("archive-project").hidden = !state.project || !isOwner();
    $("archive-project").textContent = state.project?.is_archived ? "Restaurar projeto" : "Arquivar projeto";
    $("project-content").hidden = !state.project;
    $("onboarding").hidden = Boolean(state.project);
    $("onboarding-title").textContent = state.org ? "Nenhum projeto selecionado" : "Seu trabalho começa aqui";
    $("onboarding-copy").textContent = state.org ? (isOwner() ? "Use o botão + ao lado de Projetos para criar um projeto." : "Os projetos da organização aparecerão aqui quando forem criados.") : "Crie uma organização ou selecione uma equipe para ver os projetos.";
    $("project-list").replaceChildren(...state.projects.map((project) => {
        const button = element("button", null, "project-link");
        button.type = "button";
        button.append(element("span", project.is_archived ? "▣" : "◇", "project-icon"), element("span", project.name));
        if (project.is_archived) button.append(element("small", "Arquivado"));
        if (project.id === state.project?.id) button.setAttribute("aria-current", "true");
        button.addEventListener("click", () => useProject(project));
        return button;
    }));
}

async function loadOrgs(preferredId) {
    state.orgs = await allPages(api);
    const org = state.orgs.find((item) => item.id === preferredId) || state.orgs[0];
    options($("organization"), org ? state.orgs.map((item) => [item.id, item.name]) : [["", "Nenhuma organização"]], org?.id);
    await useOrg(org);
}

async function useOrg(org) {
    const generation = ++state.orgLoad;
    ++state.taskLoad;
    state.org = org || null;
    state.project = null;
    state.projects = [];
    state.members = [];
    notice();
    renderContext();
    if (!org) return;
    const path = orgPath();
    try {
        const [projects, members] = await Promise.all([allPages(`${path}projects/`), allPages(`${path}memberships/`)]);
        if (generation !== state.orgLoad) return;
        state.projects = projects;
        state.members = members;
        useProject(projects.find((item) => !item.is_archived) || projects[0]);
    } catch (error) {
        if (generation === state.orgLoad) notice(error.message, true);
    }
}

function memberOptions(first) {
    return [["", first], ...state.members.map((member) => [member.id, member.username])];
}

function useProject(project) {
    ++state.taskLoad;
    state.project = project || null;
    state.filter = {};
    $("filters").reset();
    options($("filter-assignee"), [...memberOptions("Todos"), ["unassigned", "Sem responsável"]]);
    renderContext();
    if (project) loadTasks(1);
}

function formatDate(value) {
    return value ? value.split("-").reverse().join("/") : "Sem prazo";
}

function renderTasks(data) {
    const counts = { todo: 0, in_progress: 0, done: 0 };
    $("tasks").replaceChildren(...data.results.map((task) => {
        counts[task.status] = (counts[task.status] || 0) + 1;
        const row = element("tr");
        const title = element("td");
        title.append(element("strong", task.title));
        if (task.description) title.append(element("small", task.description));
        const status = element("td");
        status.append(element("span", states[task.status] || task.status, `badge ${task.status}`));
        const member = state.members.find((item) => item.id === task.assignee_membership_id);
        const action = element("td", null, "row-action");
        const button = element("button", isOwner() ? "Editar" : "Ver", "button quiet");
        button.setAttribute("aria-label", `${button.textContent}: ${task.title}`);
        button.addEventListener("click", () => openTask(task));
        action.append(button);
        row.append(title, status, element("td", member?.username || (task.assignee_membership_id ? "Membro" : "Sem responsável")), element("td", formatDate(task.due_date)), action);
        return row;
    }));
    for (const [key, count] of Object.entries(counts)) $(`count-${key}`).textContent = count;
    $("empty-tasks").hidden = data.results.length > 0;
    $("result-count").textContent = `${data.count} ${data.count === 1 ? "tarefa no resultado" : "tarefas no resultado"} · indicadores desta página`;
    $("prev-page").disabled = !data.previous;
    $("next-page").disabled = !data.next;
    $("page-label").textContent = `Página ${state.page}`;
}

async function loadTasks(page) {
    if (!state.project) return;
    const generation = ++state.taskLoad;
    const params = new URLSearchParams({ ...state.filter, page });
    renderTasks({ results: [], count: 0 });
    $("empty-tasks").hidden = true;
    $("result-count").textContent = "Carregando tarefas…";
    try {
        const data = await request(`${tasksPath()}?${params}`);
        if (generation !== state.taskLoad) return;
        state.page = page;
        renderTasks(data);
    } catch (error) {
        if (generation !== state.taskLoad) return;
        $("result-count").textContent = "Não foi possível carregar as tarefas.";
        notice(error.message, true);
    }
}

let saveAction;

function field(name, label, { type = "text", value = "", required = false, choices, maxlength, disabled = false } = {}) {
    const wrapper = element("label", label);
    const input = element(choices ? "select" : type === "textarea" ? "textarea" : "input");
    input.name = name;
    input.required = required;
    input.disabled = disabled;
    if (maxlength) input.maxLength = maxlength;
    if (choices) options(input, choices, value ?? "");
    else {
        if (type === "textarea") input.rows = 3;
        else input.type = type;
        if (type === "number") input.min = 1;
        input.value = value ?? "";
    }
    wrapper.append(input);
    return wrapper;
}

function openEditor(title, fields, action) {
    $("editor-title").textContent = title;
    $("editor-fields").replaceChildren(...fields);
    $("editor-error").hidden = true;
    $("save-editor").hidden = !action;
    saveAction = action;
    $("editor").showModal();
}

function openTask(task) {
    const disabled = !isOwner();
    const path = task ? `${tasksPath()}${task.id}/` : tasksPath();
    const fields = [
        field("title", "Título", { value: task?.title, required: true, maxlength: 150, disabled }),
        field("description", "Descrição", { type: "textarea", value: task?.description, maxlength: 5000, disabled }),
        field("due_date", "Prazo", { type: "date", value: task?.due_date, disabled }),
        field("assignee_membership_id", "Responsável", { choices: memberOptions("Sem responsável"), value: task?.assignee_membership_id, disabled }),
    ];
    if (task) fields.push(field("status", "Estado", { choices: Object.entries(states), value: task.status, disabled }));
    openEditor(disabled ? "Detalhes da tarefa" : task ? "Editar tarefa" : "Nova tarefa", fields, disabled ? null : async (data) => {
        data.assignee_membership_id = data.assignee_membership_id ? Number(data.assignee_membership_id) : null;
        data.due_date ||= null;
        await request(path, task ? "PATCH" : "POST", data);
        await loadTasks(1);
        notice(task ? "Tarefa atualizada." : "Tarefa criada.");
    });
}

$("organization").addEventListener("change", (event) => useOrg(state.orgs.find((org) => String(org.id) === event.target.value)));
$("add-org").addEventListener("click", () => openEditor("Nova organização", [field("name", "Nome", { required: true, maxlength: 150 })], async ({ name }) => {
    const prefix = name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 120) || "organizacao";
    const org = await request(api, "POST", { name, slug: `${prefix}-${Date.now().toString(36)}` });
    await loadOrgs(org.id);
    notice("Organização criada.");
}));
$("add-project").addEventListener("click", () => openEditor("Novo projeto", [
    field("name", "Nome", { required: true, maxlength: 150 }),
    field("description", "Descrição", { type: "textarea", maxlength: 5000 }),
], async (data) => {
    const project = await request(`${orgPath()}projects/`, "POST", data);
    state.projects.push(project);
    useProject(project);
    notice("Projeto criado.");
}));
$("add-member").addEventListener("click", () => openEditor("Adicionar membro", [
    field("user_id", "ID da conta (mostrado no topo da tela do membro)", { type: "number", required: true }),
    field("role", "Papel", { choices: [["member", "Membro"], ["owner", "Proprietário"]], value: "member" }),
], async (data) => {
    const member = await request(`${orgPath()}memberships/`, "POST", { ...data, user_id: Number(data.user_id) });
    state.members.push(member);
    options($("filter-assignee"), [...memberOptions("Todos"), ["unassigned", "Sem responsável"]], state.filter.assignee_membership_id);
    notice("Membro adicionado.");
}));
$("new-task").addEventListener("click", () => openTask(null));
$("archive-project").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const project = state.project;
    button.disabled = true;
    try {
        const updated = await request(projectPath(), "PATCH", { is_archived: !project.is_archived });
        state.projects = state.projects.map((item) => item.id === updated.id ? updated : item);
        if (state.project?.id === updated.id) state.project = updated;
        renderContext();
        notice(updated.is_archived ? "Projeto arquivado." : "Projeto restaurado.");
    } catch (error) { notice(error.message, true); }
    finally { button.disabled = false; }
});
$("filters").addEventListener("submit", (event) => {
    event.preventDefault();
    notice();
    state.filter = Object.fromEntries([...new FormData(event.currentTarget)].filter(([, value]) => value));
    loadTasks(1);
});
$("filters").addEventListener("reset", () => {
    if (Object.keys(state.filter).length) {
        state.filter = {};
        notice();
        loadTasks(1);
    }
});
$("prev-page").addEventListener("click", () => loadTasks(state.page - 1));
$("next-page").addEventListener("click", () => loadTasks(state.page + 1));
for (const id of ["close-editor", "cancel-editor"]) $(id).addEventListener("click", () => $("editor").close());
$("editor").addEventListener("cancel", (event) => { if ($("save-editor").disabled) event.preventDefault(); });
$("editor-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!saveAction || $("save-editor").disabled) return;
    const controls = [$("save-editor"), $("close-editor"), $("cancel-editor")];
    controls.forEach((button) => { button.disabled = true; });
    $("editor-error").hidden = true;
    try {
        await saveAction(Object.fromEntries(new FormData(event.currentTarget)));
        $("editor").close();
    } catch (error) {
        $("editor-error").textContent = error.message;
        $("editor-error").hidden = false;
    } finally { controls.forEach((button) => { button.disabled = false; }); }
});

loadOrgs().catch((error) => notice(error.message, true));
