const state = { catalog: null, requests: [], page: 'overview', config: null, pollTimer: null }

const $ = (selector, root = document) => root.querySelector(selector)
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)]

function tokenHeaders() {
  const headers = { 'Content-Type': 'application/json', 'X-User-Email': localStorage.getItem('factory-user') || 'developer@example.com' }
  const token = localStorage.getItem('factory-token')
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...tokenHeaders(), ...(options.headers || {}) } })
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      const detail = body.detail
      if (typeof detail === 'string') message = detail
      else if (detail?.errors) message = detail.errors.join('; ')
      else if (Array.isArray(detail)) message = detail.map(item => item.msg || 'Validation error').join('; ')
    } catch {}
    throw new Error(message)
  }
  return response.json()
}

function toast(message, error = false) {
  const element = $('#toast')
  element.textContent = message
  element.classList.toggle('error', error)
  element.classList.add('show')
  clearTimeout(window.toastTimer)
  window.toastTimer = setTimeout(() => element.classList.remove('show'), 4200)
}

function navigate(page) {
  state.page = page
  $$('.page').forEach(element => element.classList.toggle('active', element.id === `page-${page}`))
  $$('.nav-item').forEach(element => element.classList.toggle('active', element.dataset.page === page))
  window.scrollTo({ top: 0, behavior: 'smooth' })
  if (page === 'requests') loadRequests()
}

function formatDate(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;' })[character])
}

function statusClass(status) {
  const normalized = String(status || '').toUpperCase()
  if (normalized === 'READY') return 'ready'
  if (normalized === 'FAILED') return 'failed'
  return ''
}

function renderMetrics() {
  $('#totalRequests').textContent = state.requests.length
  $('#pendingRequests').textContent = state.requests.filter(item => ['REQUESTED', 'SUBMITTED', 'LOCAL_CREATED'].includes(String(item.status).toUpperCase())).length
  $('#readyRequests').textContent = state.requests.filter(item => String(item.status).toUpperCase() === 'READY').length
  $('#gpuRequests').textContent = state.requests.filter(item => item.gpu_enabled).length
}

function renderRecent() {
  const container = $('#recentRequests')
  if (!state.requests.length) {
    container.innerHTML = '<div class="empty-mini">No requests yet. Create the first one.</div>'
    return
  }
  container.innerHTML = state.requests.slice(0, 5).map(item => `
    <div class="request-row">
      <div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.project_id)}</small></div>
      <span>${escapeHtml(item.owner_team)}</span>
      <span>${escapeHtml(item.environment).toUpperCase()}</span>
      <span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span>
    </div>`).join('')
}

function filteredRequests() {
  const query = ($('#requestSearch')?.value || '').toLowerCase().trim()
  const status = $('#statusFilter')?.value || 'all'
  return state.requests.filter(item => {
    const haystack = [item.name, item.project_id, item.owner_team, item.blueprint, item.environment].join(' ').toLowerCase()
    return (!query || haystack.includes(query)) && (status === 'all' || String(item.status).toUpperCase() === status)
  })
}

function provisionButtonCell(item) {
  if (!state.config?.local_provisioning_enabled) return '<td><small>—</small></td>'
  const status = String(item.status || '').toUpperCase()
  if (status === 'PROVISIONING') {
    return `<td><button class="button secondary small" data-view-log="${escapeHtml(item.name)}">View log</button></td>`
  }
  const label = status === 'READY' ? 'Re-provision' : status === 'FAILED' ? 'Retry provision' : 'Provision'
  return `<td><button class="button primary small" data-provision="${escapeHtml(item.name)}">${label}</button></td>`
}

function renderRequestTable() {
  const rows = filteredRequests()
  const body = $('#requestTable')
  const empty = $('#requestEmpty')
  body.innerHTML = rows.map(item => `
    <tr>
      <td><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.project_id)}</small></td>
      <td>${escapeHtml(item.environment).toUpperCase()}<small>${escapeHtml(item.region)}</small></td>
      <td>${escapeHtml(item.owner_team)}</td>
      <td>${escapeHtml(item.blueprint)}</td>
      <td>${item.gpu_enabled ? '<span class="gpu-pill">H100</span>' : 'CPU'}</td>
      <td><span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td>
      <td>${formatDate(item.created_at)}</td>
      ${provisionButtonCell(item)}
    </tr>`).join('')
  empty.classList.toggle('hidden', rows.length > 0)
  $('.table-wrap').classList.toggle('hidden', rows.length === 0)
}

function openProvisionDialog(name) {
  $('#provisionClusterName').textContent = name
  $('#provisionLog').textContent = ''
  $('#provisionDialog').showModal()
  pollProvision(name)
}

async function triggerProvision(name) {
  try {
    await api(`/api/v1/requests/${encodeURIComponent(name)}/provision`, { method: 'POST' })
    toast(`Provisioning started for ${name}`)
    openProvisionDialog(name)
    await loadRequests()
  } catch (error) {
    toast(`Could not start provisioning: ${error.message}`, true)
  }
}

function pollProvision(name) {
  clearInterval(state.pollTimer)
  const tick = async () => {
    try {
      const job = await api(`/api/v1/requests/${encodeURIComponent(name)}/provision`)
      const pre = $('#provisionLog')
      pre.textContent = job.logs.join('\n')
      pre.scrollTop = pre.scrollHeight
      if (job.status !== 'running') {
        clearInterval(state.pollTimer)
        $('#provisionSubtitle').textContent = job.status === 'succeeded'
          ? 'Provisioning finished successfully.'
          : 'Provisioning failed. Review the log above.'
        toast(job.status === 'succeeded' ? `${name} is ready` : `${name} provisioning failed`, job.status !== 'succeeded')
        await loadRequests()
      }
    } catch (error) {
      clearInterval(state.pollTimer)
      toast(`Lost track of provisioning job: ${error.message}`, true)
    }
  }
  tick()
  state.pollTimer = setInterval(tick, 2000)
}

async function loadRequests(showMessage = false) {
  try {
    state.requests = await api('/api/v1/requests')
    renderMetrics()
    renderRecent()
    renderRequestTable()
    if (showMessage) toast('Request list refreshed')
  } catch (error) {
    toast(`Could not load requests: ${error.message}`, true)
  }
}

function profile() {
  return state.catalog?.profiles?.[$('#blueprint').value]
}

function selectValue(name, value) {
  const element = $(`[name="${name}"]`)
  if (element && value !== undefined && value !== null) element.value = String(value)
}

function applyBlueprintDefaults() {
  const selected = profile()
  if (!selected) return
  const form = $('#clusterForm')
  const allowed = selected.allowed_environments || []
  $$('#environment option').forEach(option => { option.disabled = !allowed.includes(option.value) })
  if (!allowed.includes(form.elements.environment.value)) form.elements.environment.value = allowed[0]
  const capacity = selected.default_capacity || {}
  Object.entries(capacity).forEach(([name, value]) => selectValue(name, value))
  const backup = selected.default_backup || {}
  selectValue('backup_tier', backup.tier)
  selectValue('retention_days', backup.retention_days)
  selectValue('target_rpo_minutes', backup.target_rpo_minutes)
  const gpu = Boolean(selected.requires_gpu)
  $('#gpuCard').classList.toggle('hidden', !gpu)
  if (gpu) {
    selectValue('gpu_machine_type', selected.gpu?.default_machine_type || 'a3-highgpu-8g')
    selectValue('accelerator_count', selected.gpu?.default_accelerator_count || 8)
  }
  const production = form.elements.environment.value === 'prod'
  form.elements.deletion_protection.checked = production || form.elements.deletion_protection.checked
}

function renderCatalog() {
  const catalog = state.catalog
  const blueprint = $('#blueprint')
  blueprint.innerHTML = Object.entries(catalog.profiles || {}).map(([id, item]) => `<option value="${escapeHtml(id)}">${escapeHtml(item.display_name)}</option>`).join('')
  const region = $('#region')
  region.innerHTML = (catalog.allowed_regions || ['us-west1']).map(item => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join('')
  blueprint.value = catalog.profiles['standard-prod-v1'] ? 'standard-prod-v1' : Object.keys(catalog.profiles)[0]
  applyBlueprintDefaults()
}

function integer(form, name, fallback = 0) {
  const value = Number.parseInt(form.elements[name].value, 10)
  return Number.isFinite(value) ? value : fallback
}

function formPayload() {
  const form = $('#clusterForm')
  const gpuEnabled = !$('#gpuCard').classList.contains('hidden')
  const backupTier = form.elements.backup_tier.value
  const networkMode = form.elements.network_mode.value
  const privateEndpointOnly = form.elements.private_endpoint_only.checked
  const payload = {
    name: form.elements.name.value.trim(),
    project_id: form.elements.project_id.value.trim(),
    blueprint: form.elements.blueprint.value,
    environment: form.elements.environment.value,
    region: form.elements.region.value,
    owner: {
      team: form.elements.team.value.trim(),
      google_group: form.elements.google_group.value.trim(),
      cost_center: form.elements.cost_center.value.trim(),
      technical_contact: form.elements.technical_contact.value.trim() || null,
    },
    workload: {
      data_classification: form.elements.data_classification.value,
      exposure: form.elements.exposure.value,
      description: form.elements.description.value.trim(),
    },
    capacity: {
      system_min_nodes: integer(form, 'system_min_nodes', 3),
      system_max_nodes: integer(form, 'system_max_nodes', 6),
      general_min_nodes: integer(form, 'general_min_nodes', 3),
      general_max_nodes: integer(form, 'general_max_nodes', 30),
      max_pods_per_node: 64,
    },
    gpu: {
      enabled: gpuEnabled,
      model: gpuEnabled ? 'nvidia-h100-80gb' : null,
      machine_type: gpuEnabled ? form.elements.gpu_machine_type.value : null,
      accelerator_count: gpuEnabled ? integer(form, 'accelerator_count', 8) : 0,
      minimum_nodes: gpuEnabled ? integer(form, 'gpu_minimum_nodes', 1) : 0,
      maximum_nodes: gpuEnabled ? integer(form, 'gpu_maximum_nodes', 4) : 0,
      zones: gpuEnabled ? form.elements.gpu_zones.value.split(',').map(value => value.trim()).filter(Boolean) : [],
      provisioning_model: gpuEnabled ? form.elements.provisioning_model.value : 'standard',
      reservation_name: gpuEnabled ? (form.elements.reservation_name.value.trim() || null) : null,
    },
    availability: {
      tier: 'regional-ha',
      application_minimum_replicas: integer(form, 'application_replicas', 3),
      secondary_region: null,
    },
    backup: {
      tier: backupTier,
      retention_days: integer(form, 'retention_days', 7),
      delete_lock_days: backupTier === 'gold' ? 7 : 0,
      target_rpo_minutes: integer(form, 'target_rpo_minutes', 1440),
      include_volume_data: backupTier !== 'none',
      include_secrets: backupTier !== 'none',
    },
    network: {
      mode: networkMode,
      host_project_id: networkMode === 'shared' ? (form.elements.host_project_id.value.trim() || null) : null,
      network_name: 'gke-platform',
      create_nat: form.elements.create_nat.checked,
      private_endpoint_only: privateEndpointOnly,
      authorized_cidrs: privateEndpointOnly ? [] : form.elements.authorized_cidrs.value.split(/[,\n]/).map(value => value.trim()).filter(Boolean),
    },
    lifecycle: {
      deletion_protection: form.elements.deletion_protection.checked,
      expiration_date: null,
    },
    labels: {
      application: form.elements.team.value.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-').slice(0, 63),
      'data-classification': form.elements.data_classification.value,
    },
  }
  return payload
}

function validationMessage(type, title, details) {
  const box = $('#validationBox')
  box.className = `validation-box ${type}`
  box.innerHTML = `<strong>${escapeHtml(title)}</strong><small>${escapeHtml(details)}</small>`
}

async function submitCluster(event) {
  event.preventDefault()
  const form = event.currentTarget
  if (!form.reportValidity()) return
  const button = $('#submitButton')
  button.disabled = true
  button.textContent = 'Validating...'
  try {
    const payload = formPayload()
    const validation = await api('/api/v1/requests/validate', { method: 'POST', body: JSON.stringify(payload) })
    const warnings = validation.warnings || []
    validationMessage(warnings.length ? 'warning' : 'success', warnings.length ? 'Valid with warnings' : 'All guardrails passed', warnings.join(' ') || 'Schema, platform policy, availability, networking, and blueprint rules passed.')
    button.textContent = 'Submitting request...'
    const result = await api('/api/v1/requests', { method: 'POST', body: JSON.stringify(payload) })
    toast(result.commit_url ? 'Request committed to main and queued for reconciliation' : 'Request created in local mode')
    form.reset()
    renderCatalog()
    syncEndpointControls()
    await loadRequests()
    navigate('requests')
  } catch (error) {
    validationMessage('error', 'Request blocked', error.message)
    toast(error.message, true)
  } finally {
    button.disabled = false
    button.textContent = 'Validate and submit →'
  }
}

function syncEndpointControls() {
  const privateOnly = $('[name="private_endpoint_only"]').checked
  const field = $('#authorizedCidrsField')
  const input = $('[name="authorized_cidrs"]')
  field.classList.toggle('hidden', privateOnly)
  input.required = !privateOnly
  if (privateOnly) input.value = ''
}

function wireEvents() {
  $$('[data-page]').forEach(element => element.addEventListener('click', () => navigate(element.dataset.page)))
  $('#blueprint').addEventListener('change', applyBlueprintDefaults)
  $('#environment').addEventListener('change', () => {
    const production = $('#environment').value === 'prod'
    if (production) $('[name="deletion_protection"]').checked = true
  })
  $('#networkMode').addEventListener('change', event => $('#hostProjectField').classList.toggle('hidden', event.target.value !== 'shared'))
  $('[name="private_endpoint_only"]').addEventListener('change', syncEndpointControls)
  $('#clusterForm').addEventListener('submit', submitCluster)
  $('#refreshRequests').addEventListener('click', () => loadRequests(true))
  $('#requestSearch').addEventListener('input', renderRequestTable)
  $('#statusFilter').addEventListener('change', renderRequestTable)
  const dialog = $('#identityDialog')
  $('#settingsButton').addEventListener('click', () => {
    $('#identityEmail').value = localStorage.getItem('factory-user') || 'developer@example.com'
    dialog.showModal()
  })
  $('#saveIdentity').addEventListener('click', () => {
    const email = $('#identityEmail').value.trim()
    if (email) localStorage.setItem('factory-user', email)
    toast(`Local identity set to ${email}`)
  })
  $('#requestTable').addEventListener('click', event => {
    const provisionName = event.target.dataset.provision
    const viewName = event.target.dataset.viewLog
    if (provisionName) triggerProvision(provisionName)
    else if (viewName) openProvisionDialog(viewName)
  })
  $('#closeProvisionDialog').addEventListener('click', () => {
    clearInterval(state.pollTimer)
    $('#provisionDialog').close()
  })
}

async function start() {
  wireEvents()
  syncEndpointControls()
  try {
    state.catalog = await api('/api/v1/catalog')
    renderCatalog()
  } catch (error) {
    toast(`Could not load blueprint catalog: ${error.message}`, true)
  }
  try {
    state.config = await api('/api/v1/config')
  } catch (error) {
    state.config = { local_provisioning_enabled: false }
  }
  await loadRequests()
}

document.addEventListener('DOMContentLoaded', start)
