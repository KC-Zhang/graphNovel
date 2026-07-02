/**
 * 临时存储待上传的书籍文件
 * 用于首页点击后立即跳转，在阅读页再进行上传/抽取
 */
import { reactive } from 'vue'

const state = reactive({
  files: [],
  bookName: '',
  isPending: false
})

export function setPendingUpload(files, bookName) {
  state.files = files
  state.bookName = bookName
  state.isPending = true
}

export function getPendingUpload() {
  return {
    files: state.files,
    bookName: state.bookName,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.bookName = ''
  state.isPending = false
}

export default state
