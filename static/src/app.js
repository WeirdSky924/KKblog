import Alpine from "alpinejs";
import "htmx.org";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowLeftToLine,
  ArrowRight,
  ArrowRightToLine,
  ArrowUp,
  ArrowUpToLine,
  Bell,
  Bold,
  Bookmark,
  BookmarkCheck,
  BriefcaseBusiness,
  CalendarX2,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleCheck,
  CircleCheckBig,
  CircleX,
  Code,
  Columns3,
  Copy,
  CornerDownLeft,
  Download,
  Ellipsis,
  Eye,
  ExternalLink,
  FileText,
  FileArchive,
  FilePlus2,
  FileUp,
  Flag,
  GitCompareArrows,
  GripVertical,
  Heading1,
  Heading2,
  Heading3,
  Heading4,
  Heading5,
  Heading6,
  History,
  ImageUp,
  Info,
  Italic,
  KeyRound,
  List,
  ListChecks,
  ListOrdered,
  ListTree,
  Link,
  LockKeyhole,
  LocateFixed,
  LogIn,
  LogOut,
  Mail,
  Menu,
  MessageCircle,
  Minus,
  MonitorSmartphone,
  Move,
  Moon,
  NotebookPen,
  Paperclip,
  Pause,
  PanelTop,
  PencilLine,
  Pencil,
  Pilcrow,
  Pin,
  PinOff,
  Play,
  Plus,
  Quote,
  Redo2,
  RefreshCw,
  RemoveFormatting,
  Replace,
  Reply,
  RotateCw,
  RotateCcw,
  Rows3,
  Save,
  Send,
  Search,
  Settings,
  ShieldCheck,
  Square,
  SquareCode,
  SquarePlay,
  Strikethrough,
  Sun,
  Table2,
  ThumbsUp,
  Trash2,
  Timer,
  TriangleAlert,
  Underline,
  Unlink,
  Undo2,
  UserPlus,
  UserRound,
  X,
  createIcons,
} from "lucide";

import { normalizeTheme, storeTheme } from "./theme-values.js";
import {
  focusLoadedCommentReply,
  initializeCommentForms,
  initializeCommentThreads,
} from "./comments.js";
import {
  destroyAuthorEditors,
  initializeAuthorEditors,
} from "./authoring-editor.js";
import { initializeArticleDraftClears } from "./authoring-local-draft.js";
import { initializeAuthorOperations } from "./authoring-operations.js";
import { initializeImportUploadForms } from "./authoring-import.js";
import {
  initializeNavigationTrees,
  initializeNodeForms,
} from "./administration-navigation.js";
import { initializeAdministrationSettings } from "./administration-settings.js";
import { initializeAdministrationOperations } from "./administration-operations.js";
import { initializeAdministrationArticlePreviews } from "./administration-article-preview.js";
import { initializeHomeNavigation } from "./home-navigation.js";
import { initializeHomeHeroMedia } from "./home-hero.js";
import { initializeArticleActions } from "./article-actions.js";
import {
  initializeBoostedPageShell,
  initializeNotificationCenters,
  initializePersonalMenus,
  initializeSiteHeaderMetrics,
} from "./site-shell.js";
import {
  initializeLiveSubmitForms,
  initializeLiveSubmitSupport,
} from "./live-submit.js";
import { initializePasswordReveals } from "./password-reveal.js";
import { initializeHeaderSearch } from "./header-search.js";
import { initializeOpportunities } from "./opportunities.js";
import {
  MediaUploadRequestError,
  uploadMediaFile,
} from "./media-upload.js";
import { initializeReadableCodeBlocks } from "./editor-code-block.js";
import { initializeEditorTagPickers } from "./editor-tag-picker.js";
import { editorUploadTrackerFor } from "./editor-upload-state.js";

const availableIcons = {
  ArrowDownToLine,
  ArrowLeft,
  ArrowLeftToLine,
  ArrowRight,
  ArrowRightToLine,
  ArrowUp,
  ArrowUpToLine,
  Bell,
  Bold,
  Bookmark,
  BookmarkCheck,
  BriefcaseBusiness,
  CalendarX2,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleCheck,
  CircleCheckBig,
  CircleX,
  Code,
  Columns3,
  Copy,
  CornerDownLeft,
  Download,
  Ellipsis,
  Eye,
  ExternalLink,
  FileText,
  FileArchive,
  FilePlus2,
  FileUp,
  Flag,
  GitCompareArrows,
  GripVertical,
  Heading1,
  Heading2,
  Heading3,
  Heading4,
  Heading5,
  Heading6,
  History,
  ImageUp,
  Info,
  Italic,
  KeyRound,
  List,
  ListChecks,
  ListOrdered,
  ListTree,
  Link,
  LockKeyhole,
  LocateFixed,
  LogIn,
  LogOut,
  Mail,
  Menu,
  MessageCircle,
  Minus,
  MonitorSmartphone,
  Move,
  Moon,
  NotebookPen,
  Paperclip,
  Pause,
  PanelTop,
  PencilLine,
  Pencil,
  Pilcrow,
  Pin,
  PinOff,
  Play,
  Plus,
  Quote,
  Redo2,
  RefreshCw,
  RemoveFormatting,
  Replace,
  Reply,
  RotateCw,
  RotateCcw,
  Rows3,
  Save,
  Send,
  Search,
  Settings,
  ShieldCheck,
  Square,
  SquareCode,
  SquarePlay,
  Strikethrough,
  Sun,
  Table2,
  ThumbsUp,
  Trash2,
  Timer,
  TriangleAlert,
  Underline,
  Unlink,
  Undo2,
  UserPlus,
  UserRound,
  X,
};
const RETURN_FOCUS_KEY = "kaj.error-return-focus";
const RETURN_FOCUS_REQUEST_KEY = "kaj.error-return-focus-requested";
let activeNotificationTrigger = null;

function writeSessionValue(key, value) {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // Session storage is optional; history navigation still works without it.
  }
}

function takeSessionValue(key) {
  try {
    const value = window.sessionStorage.getItem(key);
    window.sessionStorage.removeItem(key);
    return value;
  } catch {
    return null;
  }
}

function restoreErrorOriginFocus() {
  if (takeSessionValue(RETURN_FOCUS_REQUEST_KEY) !== "true") {
    return;
  }
  const originId = takeSessionValue(RETURN_FOCUS_KEY);
  if (!originId) {
    return;
  }
  const origin = document.getElementById(originId);
  if (origin instanceof HTMLElement) {
    requestAnimationFrame(() => origin.focus({ preventScroll: true }));
  }
}

function restoreSubmitState() {
  document.querySelectorAll("form[data-submit-once]").forEach((form) => {
    delete form.dataset.submitting;
    form.removeAttribute("aria-busy");
    form
      .querySelectorAll("button[type='submit'], input[type='submit']")
      .forEach((control) => control.removeAttribute("aria-disabled"));
  });
}

function initializeIcons(root = document) {
  createIcons({
    root,
    icons: availableIcons,
    attrs: {
      "aria-hidden": "true",
      focusable: "false",
      width: "24",
      height: "24",
    },
  });
}

function initializeCharacterCounts(root = document) {
  root.querySelectorAll?.("[data-character-count]").forEach((counter) => {
    if (!(counter instanceof HTMLElement) || counter.dataset.bound === "true") {
      return;
    }
    const field = document.getElementById(counter.dataset.characterCount || "");
    if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement)) {
      return;
    }
    counter.dataset.bound = "true";
    const update = () => {
      counter.textContent = `${field.value.length} / ${field.maxLength}`;
    };
    field.addEventListener("input", update);
    update();
  });
}

function initializePublicationForms(root = document) {
  root.querySelectorAll?.(".author-publication-form").forEach((form) => {
    if (!(form instanceof HTMLFormElement) || form.dataset.publicationBound === "true") {
      return;
    }
    form.dataset.publicationBound = "true";
    const field = form.querySelector("[data-schedule-field]");
    const input = form.elements.namedItem("scheduled_local");
    const update = () => {
      const mode = form.elements.namedItem("publication_mode");
      const scheduled = mode instanceof RadioNodeList && mode.value === "SCHEDULED";
      if (field instanceof HTMLElement) field.hidden = !scheduled;
      if (input instanceof HTMLInputElement) input.disabled = !scheduled;
    };
    form.addEventListener("change", update);
    update();
  });
}

function notificationTrigger(notificationId) {
  if (
    activeNotificationTrigger instanceof HTMLElement &&
    activeNotificationTrigger.isConnected &&
    activeNotificationTrigger.dataset.notificationTrigger === notificationId
  ) {
    return activeNotificationTrigger;
  }
  return Array.from(document.querySelectorAll("[data-notification-trigger]")).find(
    (trigger) => trigger.dataset.notificationTrigger === notificationId,
  );
}

function initializeNotificationDialogs() {
  document.querySelectorAll("[data-notification-dialog]").forEach((dialog) => {
    if (
      !(dialog instanceof HTMLDialogElement) ||
      dialog.dataset.notificationBound === "true"
    ) {
      return;
    }
    dialog.dataset.notificationBound = "true";
    const notificationId = dialog.dataset.notificationId || "";
    const origin = notificationTrigger(notificationId);
    const notificationCenter = origin?.closest("[data-notification-center]");
    if (notificationCenter instanceof HTMLDetailsElement) {
      notificationCenter.dataset.notificationDialogActive = "true";
      notificationCenter.open = true;
    }
    const closeDialog = () => {
      if (dialog.open) {
        dialog.close();
      }
    };
    dialog.querySelectorAll("[data-notification-close]").forEach((button) => {
      button.addEventListener("click", closeDialog);
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        closeDialog();
      }
    });
    dialog.addEventListener("close", () => {
      const trigger = notificationTrigger(notificationId);
      if (notificationCenter instanceof HTMLDetailsElement) {
        delete notificationCenter.dataset.notificationDialogActive;
        notificationCenter.open = true;
      }
      dialog.closest("#modal-layer")?.replaceChildren();
      activeNotificationTrigger = null;
      if (trigger instanceof HTMLElement) {
        requestAnimationFrame(() => trigger.focus({ preventScroll: true }));
      }
    });
    if (dialog.open) {
      dialog.removeAttribute("open");
    }
    dialog.showModal();
    const initialFocus = dialog.querySelector("[data-notification-close]");
    if (initialFocus instanceof HTMLElement) {
      requestAnimationFrame(() => initialFocus.focus({ preventScroll: true }));
    }
  });
}

function updateNotificationUnreadCount(value) {
  const unreadCount = Number(value);
  if (!Number.isSafeInteger(unreadCount) || unreadCount < 0) {
    return;
  }
  document.querySelectorAll("[data-notification-center]").forEach((center) => {
    center.dataset.notificationState = unreadCount === 0 ? "read" : "unread";
    const trigger = center.querySelector(".notification-center__trigger");
    trigger?.setAttribute("aria-label", `通知，${unreadCount}条未读`);
    const label = center.querySelector("[data-notification-unread-label]");
    if (label instanceof HTMLElement) {
      label.textContent = `${unreadCount}条未读`;
    }
    const badge = center.querySelector("[data-notification-badge]");
    if (badge instanceof HTMLElement) {
      badge.hidden = unreadCount === 0;
    }
  });
  document.querySelectorAll("[data-notification-unread-text]").forEach((label) => {
    label.textContent = unreadCount ? `${unreadCount} 条未读` : "已全部阅读";
  });
  document.querySelectorAll("[data-notification-mark-all]").forEach((form) => {
    form.hidden = unreadCount === 0;
  });
}

function markNotificationItemRead(notificationId) {
  if (!notificationId) {
    return;
  }
  document.querySelectorAll("[data-notification-item]").forEach((item) => {
    if (item.dataset.notificationId !== notificationId) {
      return;
    }
    item.dataset.notificationRead = "true";
    item.classList.remove("notification-item--unread");
    const state = item.querySelector("[data-notification-state]");
    if (state instanceof HTMLElement) {
      state.textContent = "已读";
    }
  });
}

function initializeConfirmDialogs(root = document) {
  root.querySelectorAll?.("[data-confirm-dialog]").forEach((dialog) => {
    if (!(dialog instanceof HTMLDialogElement)) {
      return;
    }
    if (dialog.dataset.bound !== "true") {
      dialog.dataset.bound = "true";
      dialog.querySelectorAll("[data-dialog-cancel]").forEach((button) => {
        button.addEventListener("click", () => {
          dialog.close("cancel");
        });
      });
      dialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        dialog.close("cancel");
      });
      dialog.addEventListener("keydown", (event) => {
        if (event.key !== "Tab") return;
        const focusable = Array.from(
          dialog.querySelectorAll(
            'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ),
        ).filter((element) =>
          element instanceof HTMLElement &&
          !element.hidden &&
          element.getAttribute("aria-hidden") !== "true" &&
          element.getClientRects().length > 0
        );
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      });
      dialog.addEventListener("close", () => {
        const returnFocusId = dialog.dataset.dialogReturnFocus || "";
        const trigger =
          (returnFocusId && document.getElementById(returnFocusId)) ||
          (dialog.id
            ? document.querySelector(
                `[data-dialog-trigger][aria-controls="${dialog.id}"]`,
              )
            : document.querySelector("[data-dialog-trigger]"));
        if (dialog.returnValue === "cancel") {
          if (dialog.dataset.dialogReturnUrl) {
            window.history.replaceState(
              null,
              "",
              dialog.dataset.dialogReturnUrl,
            );
          } else {
            const url = new URL(window.location.href);
            url.searchParams.delete("confirm");
            url.hash =
              trigger instanceof HTMLElement
                ? trigger.dataset.dialogReturnHash || ""
                : "";
            window.history.replaceState(null, "", url);
          }
        }
        if (trigger instanceof HTMLElement) {
          requestAnimationFrame(() => trigger.focus({ preventScroll: true }));
        }
      });
    }
    if (dialog.hasAttribute("data-auto-modal")) {
      if (!dialog.isConnected) {
        return;
      }
      if (dialog.open) {
        dialog.removeAttribute("open");
      }
      dialog.showModal();
      const initialFocus =
        dialog.querySelector("[data-error-focus]") ||
        dialog.querySelector("[autofocus]") ||
        dialog.querySelector("[data-dialog-cancel]");
      if (initialFocus instanceof HTMLElement) {
        window.requestAnimationFrame(() => {
          if (dialog.open) {
            initialFocus.focus({ preventScroll: true });
          }
        });
      }
    }
  });
}

function setMediaPickerState(picker, state) {
  const order = ["select", "validate", "ready"];
  const activeIndex =
    state === "ready" ? 2 : state === "uploading" || state === "error" ? 1 : 0;
  picker.dataset.mediaState = state;
  if (state === "uploading") {
    picker.setAttribute("aria-busy", "true");
  } else {
    picker.removeAttribute("aria-busy");
  }
  picker.querySelectorAll("[data-media-step]").forEach((step) => {
    const index = order.indexOf(step.dataset.mediaStep);
    step.toggleAttribute("data-complete", index >= 0 && index < activeIndex);
    if (index === activeIndex) {
      step.setAttribute("aria-current", "step");
    } else {
      step.removeAttribute("aria-current");
    }
  });
}

function initializeMediaPickers(root = document) {
  root.querySelectorAll?.("[data-media-picker]").forEach((picker) => {
    if (!(picker instanceof HTMLElement) || picker.dataset.bound === "true") {
      return;
    }
    picker.dataset.bound = "true";
    const input = picker.querySelector("[data-media-file]");
    const choose = picker.querySelector("[data-media-choose]");
    const value = picker.querySelector("[data-media-value]");
    const preview = picker.querySelector("[data-media-preview]");
    const heroImagePreview = picker.querySelector("[data-media-image-preview]");
    const heroVideoPreview = picker.querySelector("[data-media-video-preview]");
    const fileName = picker.querySelector("[data-media-file-name]");
    const fileSize = picker.querySelector("[data-media-file-size]");
    const empty = picker.querySelector("[data-media-empty]");
    const dropzone = picker.querySelector("[data-media-dropzone]");
    const result = picker.querySelector("[data-media-result]");
    const retry = picker.querySelector("[data-media-retry]");
    const attachmentInsert = picker.querySelector(
      "[data-attachment-card-insert]",
    );
    const remove = picker.querySelector("[data-media-remove]");
    const progressWrap = picker.querySelector("[data-media-progress-wrap]");
    const progress = picker.querySelector("[data-media-progress]");
    const csrf = picker.querySelector("input[name='csrfmiddlewaretoken']");
    const uploadTracker = editorUploadTrackerFor(picker);
    if (
      !(input instanceof HTMLInputElement) ||
      !(value instanceof HTMLInputElement) ||
      !(preview instanceof HTMLElement) ||
      !(result instanceof HTMLElement) ||
      !(progress instanceof HTMLProgressElement)
    ) {
      return;
    }

    let selectedFile = null;
    let previewUrl = null;
    let uploadController = null;
    const isAttachment = picker.dataset.mediaKind === "attachment";
    const isHero = picker.dataset.mediaKind === "hero";
    const mediaLabel = isAttachment ? "附件" : isHero ? "主视觉媒体" : "图片";
    const pickerLabel =
      picker.querySelector(".media-picker__header h3")?.textContent?.trim() ||
      mediaLabel;
    const favicon = document.querySelector("[data-site-favicon]");

    const announceUpload = (message, level = "success") => {
      document.dispatchEvent(
        new CustomEvent("kaj:feedback", {
          detail: {
            key: `media-upload-${picker.dataset.mediaPicker || "asset"}`,
            level,
            message,
            timeout: level === "error" ? 6500 : 4500,
          },
        }),
      );
    };

    const clearPreviewUrl = () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }
    };

    const showSelectedPreview = (file) => {
      clearPreviewUrl();
      if (isAttachment) {
        preview.hidden = false;
        if (fileName instanceof HTMLElement) fileName.textContent = file.name;
        if (fileSize instanceof HTMLElement) {
          fileSize.textContent = `${(file.size / 1024 / 1024).toFixed(2)} MiB`;
          fileSize.hidden = false;
        }
        if (empty instanceof HTMLElement) empty.hidden = true;
        return;
      }
      if (isHero) {
        const selectedVideo =
          file.type.startsWith("video/") || /\.(mp4|webm)$/i.test(file.name);
        preview.hidden = false;
        if (
          !(heroImagePreview instanceof HTMLImageElement) ||
          !(heroVideoPreview instanceof HTMLVideoElement)
        ) {
          return;
        }
        heroImagePreview.hidden = true;
        heroImagePreview.removeAttribute("src");
        heroImagePreview.alt = "";
        heroVideoPreview.pause();
        heroVideoPreview.hidden = true;
        heroVideoPreview.removeAttribute("src");
        heroVideoPreview.load();
        if (empty instanceof HTMLElement) empty.hidden = false;
        previewUrl = URL.createObjectURL(file);
        if (selectedVideo) {
          heroVideoPreview.onloadedmetadata = () => {
            heroVideoPreview.hidden = false;
            if (empty instanceof HTMLElement) empty.hidden = true;
          };
          heroVideoPreview.onerror = () => {
            heroVideoPreview.hidden = true;
            if (empty instanceof HTMLElement) empty.hidden = false;
          };
          heroVideoPreview.src = previewUrl;
          heroVideoPreview.load();
        } else {
          heroImagePreview.onload = () => {
            heroImagePreview.alt = "所选主视觉图片预览";
            heroImagePreview.hidden = false;
            if (empty instanceof HTMLElement) empty.hidden = true;
          };
          heroImagePreview.onerror = () => {
            heroImagePreview.hidden = true;
            if (empty instanceof HTMLElement) empty.hidden = false;
          };
          heroImagePreview.src = previewUrl;
        }
        return;
      }
      if (!(preview instanceof HTMLImageElement)) return;
      previewUrl = URL.createObjectURL(file);
      preview.hidden = true;
      preview.alt = "";
      if (empty instanceof HTMLElement) {
        empty.hidden = false;
      }
      preview.onload = () => {
        preview.alt = "所选图片预览";
        preview.hidden = false;
        if (empty instanceof HTMLElement) {
          empty.hidden = true;
        }
      };
      preview.onerror = () => {
        preview.removeAttribute("src");
        preview.alt = "";
        preview.hidden = true;
        if (empty instanceof HTMLElement) {
          empty.hidden = false;
        }
      };
      preview.src = previewUrl;
    };

    const setControlsBusy = (busy) => {
      input.disabled = busy;
      choose?.toggleAttribute("disabled", busy);
      retry?.toggleAttribute("disabled", busy);
      remove?.toggleAttribute("disabled", busy);
      dropzone?.toggleAttribute("aria-disabled", busy);
      if (progressWrap instanceof HTMLElement) {
        progressWrap.hidden = !busy;
      }
    };

    const showClientError = (message) => {
      result.replaceChildren();
      if (uploadTracker) retry?.setAttribute("hidden", "");
      else retry?.removeAttribute("hidden");
      setMediaPickerState(picker, "error");
      announceUpload(message, "error");
    };

    const upload = async () => {
      if (!(selectedFile instanceof File)) {
        return;
      }
      const activeFile = selectedFile;
      const controller = new AbortController();
      uploadController = controller;
      const uploadTask = uploadTracker?.begin({
        key: `picker-${picker.dataset.mediaPicker || "asset"}`,
        label: `${pickerLabel} · ${activeFile.name}`,
        onCancel: () => controller.abort(),
        onRetry: () => upload(),
      });
      setControlsBusy(true);
      retry?.setAttribute("hidden", "");
      remove?.setAttribute("hidden", "");
      progress.value = 0;
      setMediaPickerState(picker, "uploading");
      try {
        const requestUpload = () =>
          uploadMediaFile({
            file: activeFile,
            url: picker.dataset.mediaUploadUrl || "",
            csrfToken: csrf instanceof HTMLInputElement ? csrf.value : "",
            mediaLabel,
            signal: controller.signal,
            onProgress: (value) => {
              progress.value = value;
              uploadTask?.progress(value);
            },
          });
        const { assetId } = await (
          uploadTracker ? uploadTracker.schedule(requestUpload) : requestUpload()
        );
        result.replaceChildren();
        value.value = assetId;
        if (isAttachment) {
          picker.dataset.mediaCurrentName = activeFile.name;
          picker.dataset.mediaCurrentSize = String(activeFile.size);
          picker.dataset.mediaCurrentMime = activeFile.type;
          attachmentInsert?.removeAttribute("hidden");
        }
        value.dispatchEvent(new Event("input", { bubbles: true }));
        progress.value = 100;
        remove?.removeAttribute("hidden");
        retry?.setAttribute("hidden", "");
        setMediaPickerState(picker, "ready");
        picker.dispatchEvent(
          new CustomEvent("kaj:media-ready", {
            bubbles: true,
            detail: {
              adapter: picker.dataset.mediaPicker,
              assetId,
              inputName: picker.dataset.mediaInputName,
              file: activeFile,
            },
          }),
        );
        if (
          picker.dataset.mediaFavicon === "true" &&
          favicon instanceof HTMLLinkElement &&
          previewUrl
        ) {
          favicon.href = previewUrl;
        }
        announceUpload(`${pickerLabel}上传成功，可以继续保存。`);
        uploadTask?.success(`${pickerLabel}上传完成`);
      } catch (error) {
        if (
          error instanceof MediaUploadRequestError &&
          error.code === "aborted"
        ) {
          setMediaPickerState(picker, selectedFile ? "select" : "empty");
          uploadTask?.cancelled(`${pickerLabel}上传已取消`);
          announceUpload(`${pickerLabel}上传已取消。`, "info");
        } else {
          const message =
            error instanceof Error
              ? error.message
              : `${pickerLabel}上传未完成，请重试。`;
          uploadTask?.error(message);
          showClientError(message);
        }
      } finally {
        if (uploadController === controller) uploadController = null;
        setControlsBusy(false);
      }
    };

    const select = (file) => {
      if (input.disabled || !(file instanceof File)) {
        return;
      }
      selectedFile = file;
      result.replaceChildren();
      showSelectedPreview(file);
      setMediaPickerState(picker, "select");
      upload();
    };

    input.addEventListener("change", () => select(input.files?.[0]));
    choose?.addEventListener("click", () => input.click());
    retry?.addEventListener("click", upload);
    remove?.addEventListener("click", () => {
      selectedFile = null;
      input.value = "";
      value.value = "";
      if (isAttachment) {
        delete picker.dataset.mediaCurrentName;
        delete picker.dataset.mediaCurrentSize;
        delete picker.dataset.mediaCurrentMime;
        attachmentInsert?.setAttribute("hidden", "");
      }
      value.dispatchEvent(new Event("input", { bubbles: true }));
      result.replaceChildren();
      retry?.setAttribute("hidden", "");
      remove.setAttribute("hidden", "");
      clearPreviewUrl();
      if (preview instanceof HTMLImageElement) {
        preview.removeAttribute("src");
        preview.alt = "";
      }
      if (isHero) {
        if (heroImagePreview instanceof HTMLImageElement) {
          heroImagePreview.removeAttribute("src");
          heroImagePreview.alt = "";
          heroImagePreview.hidden = true;
        }
        if (heroVideoPreview instanceof HTMLVideoElement) {
          heroVideoPreview.pause();
          heroVideoPreview.removeAttribute("src");
          heroVideoPreview.load();
          heroVideoPreview.hidden = true;
        }
      }
      preview.hidden = true;
      if (fileName instanceof HTMLElement) fileName.textContent = "";
      if (fileSize instanceof HTMLElement) {
        fileSize.textContent = "";
        fileSize.hidden = true;
      }
      if (empty instanceof HTMLElement) {
        empty.hidden = false;
      }
      if (picker.dataset.mediaFavicon === "true" && favicon instanceof HTMLLinkElement) {
        favicon.href = favicon.dataset.defaultHref || favicon.href;
      }
      setMediaPickerState(picker, "empty");
      if (choose instanceof HTMLElement) {
        choose.focus();
      }
    });

    if (dropzone instanceof HTMLElement) {
      ["dragenter", "dragover"].forEach((name) => {
        dropzone.addEventListener(name, (event) => {
          event.preventDefault();
          dropzone.dataset.dragActive = "true";
        });
      });
      ["dragleave", "drop"].forEach((name) => {
        dropzone.addEventListener(name, (event) => {
          event.preventDefault();
          delete dropzone.dataset.dragActive;
        });
      });
      dropzone.addEventListener("drop", (event) => {
        select(event.dataTransfer?.files?.[0]);
      });
    }

    picker.closest("form")?.addEventListener("submit", (event) => {
      if (picker.dataset.mediaState === "uploading") {
        event.preventDefault();
        if (uploadTracker) uploadTracker.announcePending();
        else {
          showClientError(`请等待${mediaLabel}校验完成后再保存。`);
          retry?.setAttribute("hidden", "");
          setMediaPickerState(picker, "uploading");
        }
      }
    });
    setMediaPickerState(picker, value.value ? "ready" : "empty");
  });
}

function applyTheme(value, { persist = true } = {}) {
  const theme = normalizeTheme(value);
  if (!theme) {
    return false;
  }
  document.documentElement.dataset.theme = theme;
  if (persist) {
    storeTheme(theme);
  }
  document.querySelectorAll("[data-theme-value]").forEach((control) => {
    const selected = control.getAttribute("data-theme-value") === theme;
    if (control.hasAttribute("aria-pressed")) {
      control.setAttribute("aria-pressed", String(selected));
    }
    if (control instanceof HTMLInputElement) {
      control.checked = selected;
    }
  });
  document.dispatchEvent(
    new CustomEvent("kaj:theme-changed", { detail: { theme } }),
  );
  return true;
}

const feedbackLevels = new Set(["error", "info", "success", "warning"]);
const feedbackIcons = {
  error: "circle-x",
  info: "info",
  success: "circle-check",
  warning: "triangle-alert",
};

function announceShellFeedback(message, options = {}) {
  const region = document.getElementById("global-feedback");
  if (!(region instanceof HTMLElement) || typeof message !== "string" || !message) {
    return;
  }
  const level = feedbackLevels.has(options.level) ? options.level : "info";
  const key = typeof options.key === "string" ? options.key : "";
  const timeout = Number.isFinite(options.timeout)
    ? Math.min(Math.max(options.timeout, 0), 10_000)
    : 0;
  if (key) {
    Array.from(region.querySelectorAll("[data-feedback-item]")).find(
      (candidate) => candidate.dataset.feedbackKey === key,
    )?.remove();
  }
  const item = document.createElement("div");
  item.className = `feedback-item feedback-item--${level}`;
  item.dataset.feedbackItem = "";
  item.dataset.feedbackKey = key;
  item.setAttribute("role", level === "error" ? "alert" : "status");
  if (timeout > 0) {
    item.classList.add("feedback-item--transient");
  }
  const icon = document.createElement("span");
  icon.className = "feedback-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = `<i data-lucide="${feedbackIcons[level]}"></i>`;
  const text = document.createElement("p");
  text.textContent = message;
  const close = document.createElement("button");
  close.className = "icon-button feedback-dismiss";
  close.type = "button";
  close.dataset.feedbackDismiss = "";
  close.setAttribute("aria-label", "关闭这条反馈");
  close.title = "关闭";
  close.innerHTML = '<i data-lucide="x"></i>';
  item.append(icon, text, close);
  region.append(item);
  initializeIcons(item);
  if (timeout > 0) {
    const dismiss = () => {
      if (!item.isConnected) {
        return;
      }
      if (item.matches(":hover") || item.contains(document.activeElement)) {
        window.setTimeout(dismiss, 1000);
        return;
      }
      item.remove();
    };
    window.setTimeout(dismiss, timeout);
  }
}

function announceShellError(message) {
  announceShellFeedback(message, { level: "error" });
}

async function syncAccountTheme(form, submitter) {
  if (!(submitter instanceof HTMLButtonElement) || form.dataset.syncing === "true") {
    return;
  }
  const selectedTheme = normalizeTheme(submitter.value);
  const previousTheme = normalizeTheme(form.dataset.currentTheme) ?? "light";
  const syncUrl = form.dataset.themeSyncUrl;
  if (!selectedTheme || !syncUrl) {
    return;
  }
  form.dataset.syncing = "true";
  form.setAttribute("aria-busy", "true");
  form.querySelectorAll("button").forEach((button) => {
    button.disabled = true;
  });
  const body = new FormData(form);
  body.set("theme", selectedTheme);
  try {
    const response = await fetch(syncUrl, {
      method: "POST",
      body,
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!response.ok) {
      throw new Error("theme sync failed");
    }
    form.dataset.currentTheme = selectedTheme;
  } catch {
    applyTheme(previousTheme);
    announceShellError("主题偏好未能保存，请重试。");
  } finally {
    delete form.dataset.syncing;
    form.removeAttribute("aria-busy");
    form.querySelectorAll("button").forEach((button) => {
      button.disabled = false;
    });
  }
}

function currentSwapRoot(root) {
  if (root instanceof HTMLElement && root.id) {
    return document.getElementById(root.id) ?? root;
  }
  return root;
}

let pendingHomeArticleRefreshTarget = null;

function focusInsertedError(root) {
  const current = currentSwapRoot(root);
  const error = current.querySelector?.("[data-error-focus]");
  if (error instanceof HTMLElement) {
    requestAnimationFrame(() => error.focus());
  }
}

function focusSwappedRegion(root, event) {
  const current = currentSwapRoot(root);
  const trigger = event?.detail?.requestConfig?.elt;
  const refreshTargetMatches =
    typeof pendingHomeArticleRefreshTarget === "string" &&
    current instanceof HTMLElement &&
    current.matches(pendingHomeArticleRefreshTarget);
  if (
    (trigger instanceof HTMLElement &&
      trigger.matches("[data-home-article-refresh]")) ||
    refreshTargetMatches
  ) {
    pendingHomeArticleRefreshTarget = null;
    requestAnimationFrame(() => {
      current
        ?.querySelector("[data-home-article-refresh]")
        ?.focus({ preventScroll: true });
    });
    return;
  }
  if (
    !(root instanceof HTMLElement) ||
    !root.matches("[data-focus-after-swap]") ||
    current.querySelector("[data-error-focus]")
  ) {
    return;
  }
  requestAnimationFrame(() => current?.focus({ preventScroll: true }));
}

function syncHomeArticleRefreshUrl() {
  const control = document.querySelector("[data-home-article-refresh]");
  if (!(control instanceof HTMLButtonElement)) {
    return;
  }
  control.setAttribute("hx-get", `${window.location.pathname}${window.location.search}`);
}

function updateTagSelectionCount(form) {
  const status = form.querySelector("[data-tag-selection-count]");
  if (!(status instanceof HTMLElement)) {
    return;
  }
  const count = form.querySelectorAll("input[name='tags']:checked").length;
  status.textContent = `已选择 ${count} / 5`;
  if (count > 5) {
    status.dataset.overLimit = "true";
  } else {
    delete status.dataset.overLimit;
  }
}

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement) || target.name !== "tags") {
    return;
  }
  const form = target.closest("[data-tag-filter]");
  if (form instanceof HTMLFormElement) {
    updateTagSelectionCount(form);
  }
});

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }

  const notification = target.closest("[data-notification-trigger]");
  if (notification instanceof HTMLElement) {
    activeNotificationTrigger = notification;
  }

  const back = target.closest("[data-error-back]");
  if (back) {
    if (window.history.length > 1) {
      writeSessionValue(RETURN_FOCUS_REQUEST_KEY, "true");
      window.history.back();
    } else {
      window.location.assign("/");
    }
    return;
  }

  if (target.closest("[data-error-retry], [data-maintenance-retry]")) {
    window.location.reload();
    return;
  }

  if (target.closest("[data-comment-reload]")) {
    window.location.reload();
    return;
  }

  const dismiss = target.closest("[data-feedback-dismiss]");
  if (dismiss) {
    const item = dismiss.closest("[data-feedback-item]");
    const region = item?.closest("#global-feedback");
    item?.remove();
    if (event.detail === 0 && region instanceof HTMLElement) {
      region.focus({ preventScroll: true });
    }
    return;
  }

  const themeControl = target.closest("[data-theme-value]");
  if (themeControl) {
    applyTheme(themeControl.getAttribute("data-theme-value"));
    return;
  }

  const errorOrigin = target.closest("[data-error-origin]");
  if (errorOrigin instanceof HTMLElement) {
    if (!errorOrigin.id) {
      errorOrigin.id = `error-origin-${Date.now().toString(36)}`;
    }
    writeSessionValue(RETURN_FOCUS_KEY, errorOrigin.id);
  }
});

document.addEventListener("kaj:theme-request", (event) => {
  applyTheme(event.detail?.theme);
});

document.addEventListener("kaj:feedback", (event) => {
  announceShellFeedback(event.detail?.message, event.detail);
});

document.addEventListener("kaj:focus", (event) => {
  const focusId = event.detail?.id;
  if (typeof focusId !== "string" || !focusId) return;
  requestAnimationFrame(() => {
    document.getElementById(focusId)?.focus({ preventScroll: true });
  });
});

document.addEventListener("kaj:editor-preview", (event) => {
  initializeIcons(event.detail?.root ?? document);
});

document.addEventListener("kaj:media-library", (event) => {
  initializeIcons(event.detail?.root ?? document);
});

document.addEventListener("kaj:notification-read", (event) => {
  const notificationId = event.detail?.notificationId;
  if (notificationId) {
    markNotificationItemRead(notificationId);
  } else {
    document.querySelectorAll("[data-notification-item]").forEach((item) => {
      markNotificationItemRead(item.dataset.notificationId);
    });
  }
  updateNotificationUnreadCount(event.detail?.unreadCount);
});

document.addEventListener("kaj:administration-attention-read", (event) => {
  const key = event.detail?.key;
  const count = Number(event.detail?.count);
  const notificationUnreadCount = Number(
    event.detail?.notificationUnreadCount,
  );
  if (typeof key !== "string" || !Number.isInteger(count) || count < 0) {
    return;
  }
  if (
    Number.isInteger(notificationUnreadCount) &&
    notificationUnreadCount >= 0
  ) {
    updateNotificationUnreadCount(notificationUnreadCount);
  }
  document.querySelectorAll("[data-opportunity-run-attention]").forEach((badge) => {
    badge.remove();
  });
  document.querySelectorAll("[data-opportunity-run-read-form]").forEach((form) => {
    form.remove();
  });
  document
    .querySelectorAll(`[data-admin-navigation-key="${CSS.escape(key)}"]`)
    .forEach((link) => {
      const badge = link.querySelector(".administration-navigation__review-count");
      if (count === 0) {
        badge?.remove();
        link.classList.remove("administration-navigation__link--review");
        return;
      }
      if (badge) {
        badge.setAttribute("aria-label", `${count} 项待处理`);
        const value = badge.querySelector("[aria-hidden='true']");
        if (value) value.textContent = String(count);
      }
    });
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form instanceof HTMLFormElement && form.matches("[data-theme-bridge]")) {
    if (form.dataset.themeSyncUrl) {
      event.preventDefault();
      syncAccountTheme(form, event.submitter);
    }
    return;
  }
  if (
    event.defaultPrevented ||
    !(form instanceof HTMLFormElement) ||
    !form.hasAttribute("data-submit-once")
  ) {
    return;
  }
  if (form.dataset.submitting === "true") {
    event.preventDefault();
    return;
  }
  form.dataset.submitting = "true";
  form.setAttribute("aria-busy", "true");
  form.querySelectorAll("button[type='submit'], input[type='submit']").forEach((control) => {
    control.setAttribute("aria-disabled", "true");
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") {
    return;
  }
  const disclosure = document.querySelector(
    ".site-header details[open]:focus-within",
  );
  if (disclosure instanceof HTMLDetailsElement) {
    disclosure.open = false;
    disclosure.querySelector("summary")?.focus();
  }
});

document.addEventListener("click", (event) => {
  if (!(event.target instanceof Node)) {
    return;
  }
  document.querySelectorAll(".site-header details[open]").forEach((disclosure) => {
    if (
      disclosure.dataset.notificationDialogActive !== "true" &&
      !disclosure.contains(event.target)
    ) {
      disclosure.removeAttribute("open");
    }
  });
});

document.addEventListener("htmx:afterSwap", (event) => {
  const root = currentSwapRoot(event.detail?.target ?? document);
  initializeIcons(root);
  initializeSiteHeaderMetrics(root);
  initializePersonalMenus(root);
  initializeNotificationCenters(root);
  initializeNotificationDialogs();
  initializeConfirmDialogs(root);
  initializeArticleActions(root);
  initializeReadableCodeBlocks(root);
  initializeCharacterCounts(root);
  initializePublicationForms(root);
  initializePasswordReveals(root);
  initializeArticleDraftClears(root);
  initializeAuthorEditors(root);
  initializeEditorTagPickers(root);
  initializeMediaPickers(root);
  initializeCommentForms(root);
  initializeCommentThreads(root);
  initializeAuthorOperations(root);
  initializeImportUploadForms(root);
  initializeNodeForms(root);
  initializeNavigationTrees(root);
  initializeHomeHeroMedia(root);
  initializeHomeNavigation(root);
  initializeHeaderSearch(root);
  initializeAdministrationSettings(root);
  initializeAdministrationOperations(root);
  initializeAdministrationArticlePreviews(root);
  initializeOpportunities(root);
  initializeLiveSubmitForms(root);
  focusInsertedError(root);
  focusSwappedRegion(root);
});

document.addEventListener("htmx:load", (event) => {
  const root = event.detail?.elt ?? document;
  initializeSiteHeaderMetrics(root);
  initializeCommentThreads(root);
  initializeNodeForms(root);
  initializeNavigationTrees(root);
  initializeHomeHeroMedia(root);
  initializeHomeNavigation(root);
  initializeHeaderSearch(root);
  initializeArticleActions(root);
  initializePasswordReveals(root);
  initializeAdministrationOperations(root);
  initializeAdministrationArticlePreviews(root);
  initializeOpportunities(root);
  initializeLiveSubmitForms(root);
});

document.addEventListener("htmx:beforeRequest", (event) => {
  const trigger = event.detail?.elt?.closest?.("[data-notification-trigger]");
  if (trigger instanceof HTMLElement) {
    activeNotificationTrigger = trigger;
  }
});

function notifyAuthorCloudFailure(event) {
  const status = event.detail?.xhr?.status ?? 0;
  if (status !== 0 && status < 500) return;
  const form = event.detail?.elt?.closest?.("form[data-author-editor]");
  if (form instanceof HTMLFormElement) {
    form.dispatchEvent(new CustomEvent("kaj:cloud-save-failed"));
  }
}

document.addEventListener("htmx:sendError", notifyAuthorCloudFailure);
document.addEventListener("htmx:responseError", notifyAuthorCloudFailure);
document.addEventListener("htmx:timeout", notifyAuthorCloudFailure);

document.addEventListener("htmx:beforeCleanupElement", (event) => {
  destroyAuthorEditors(event.detail?.elt ?? event.target);
});

document.addEventListener("htmx:afterSettle", (event) => {
  const root = currentSwapRoot(event.detail?.target ?? document);
  focusInsertedError(root);
  focusSwappedRegion(root, event);
  focusLoadedCommentReply(root);
  syncHomeArticleRefreshUrl();
});

document.addEventListener("htmx:beforeRequest", (event) => {
  const control = event.detail?.elt?.closest?.("[data-home-article-refresh]");
  if (control instanceof HTMLButtonElement) {
    pendingHomeArticleRefreshTarget =
      control.getAttribute("hx-target") || "#home-article-region";
    control.disabled = true;
    control.setAttribute("aria-busy", "true");
  }
});

document.addEventListener("htmx:beforeSwap", (event) => {
  if (
    event.detail.xhr.status === 422 ||
    event.detail.xhr.status === 409 ||
    event.detail.xhr.status === 429 ||
    event.detail.xhr.getResponseHeader("X-Kaj-Inline-Error") === "true"
  ) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});

document.addEventListener("htmx:afterRequest", (event) => {
  const refreshControl = event.detail?.elt?.closest?.("[data-home-article-refresh]");
  if (refreshControl instanceof HTMLButtonElement) {
    refreshControl.disabled = false;
    refreshControl.removeAttribute("aria-busy");
    if (event.detail?.successful === false) {
      pendingHomeArticleRefreshTarget = null;
      requestAnimationFrame(() => refreshControl.focus({ preventScroll: true }));
      announceShellFeedback("文章列表刷新失败，请稍后重试。", {
        key: "home-article-refresh",
        level: "error",
        timeout: 5000,
      });
    }
  }
  const form = event.detail?.elt?.closest?.("form[data-submit-once]");
  if (form instanceof HTMLFormElement) {
    delete form.dataset.submitting;
    form.removeAttribute("aria-busy");
    form
      .querySelectorAll("button[type='submit'], input[type='submit']")
      .forEach((control) => control.removeAttribute("aria-disabled"));
  }
});

window.addEventListener("pageshow", () => {
  restoreSubmitState();
  restoreErrorOriginFocus();
  syncHomeArticleRefreshUrl();
});

window.addEventListener("popstate", syncHomeArticleRefreshUrl);

document.querySelectorAll("[data-opportunity-feedback]").forEach((item) => {
  const message = item.dataset.message;
  if (message) {
    announceShellFeedback(message, {
      key: "opportunity-admin",
      level: "success",
      timeout: 4000,
    });
  }
});

window.Alpine = Alpine;
Alpine.start();
initializeIcons();
initializeBoostedPageShell();
initializeSiteHeaderMetrics();
initializePersonalMenus();
initializeNotificationCenters();
initializeNotificationDialogs();
initializeConfirmDialogs();
initializeArticleActions();
initializeReadableCodeBlocks();
initializeCharacterCounts();
initializePublicationForms();
initializePasswordReveals();
initializeArticleDraftClears();
initializeAuthorEditors();
initializeEditorTagPickers();
initializeMediaPickers();
initializeCommentForms();
initializeAuthorOperations();
initializeImportUploadForms();
initializeNodeForms();
initializeNavigationTrees();
initializeHomeHeroMedia();
initializeHomeNavigation();
initializeHeaderSearch();
initializeAdministrationSettings();
initializeAdministrationOperations();
initializeAdministrationArticlePreviews();
initializeOpportunities();
initializeLiveSubmitSupport();
initializeLiveSubmitForms();
focusInsertedError(document);
applyTheme(document.documentElement.dataset.theme, { persist: false });
