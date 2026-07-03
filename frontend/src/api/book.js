import service, { requestWithRetry } from './index'

/**
 * 上传书籍文件（PDF/EPUB/TXT/MD），解析并分章
 * @param {FormData} formData - files, book_name
 * @returns {Promise}
 */
export function uploadBook(formData) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/upload',
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  )
}

/**
 * 确保章节 0..upto 已（或正在）被抽取（按需增量、可重复调用以抬高目标）
 * @param {String} projectId
 * @param {Number} upto - 目标章节索引
 * @returns {Promise}
 */
export function ensureExtraction(projectId, upto) {
  return service({
    url: '/api/graph/extract',
    method: 'post',
    data: { project_id: projectId, upto }
  })
}

/**
 * 查询增量抽取进度
 * @param {String} projectId
 * @returns {Promise}
 */
export function getExtractStatus(projectId) {
  return service({
    url: `/api/graph/status/${projectId}`,
    method: 'get'
  })
}

/**
 * 获取图谱数据（含 first_episode 与 mentions）
 * @param {String} projectId
 * @returns {Promise}
 */
export function getGraphData(projectId) {
  return service({
    url: `/api/graph/data/${projectId}`,
    method: 'get'
  })
}

/**
 * 获取单章正文
 * @param {String} projectId
 * @param {Number} idx
 * @returns {Promise}
 */
export function getEpisode(projectId, idx) {
  return service({
    url: `/api/graph/episode/${projectId}/${idx}`,
    method: 'get'
  })
}

/**
 * 获取书籍项目详情
 * @param {String} projectId
 * @returns {Promise}
 */
export function getBook(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}

/**
 * 列出所有书籍
 * @param {Number} limit
 * @returns {Promise}
 */
export function listBooks(limit = 50) {
  return service({
    url: '/api/graph/project/list',
    method: 'get',
    params: { limit }
  })
}

/**
 * 删除书籍
 * @param {String} projectId
 * @returns {Promise}
 */
export function deleteBook(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'delete'
  })
}

/**
 * 重置书籍图谱抽取状态
 * @param {String} projectId
 * @returns {Promise}
 */
export function resetBook(projectId) {
  return service({
    url: `/api/graph/project/${projectId}/reset`,
    method: 'post'
  })
}

/**
 * 从已提取文本重建章节元数据，并清空旧图谱
 * @param {String} projectId
 * @returns {Promise}
 */
export function repairBook(projectId) {
  return service({
    url: `/api/graph/project/${projectId}/repair`,
    method: 'post'
  })
}
