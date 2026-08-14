const boundHeroVideos = new WeakSet();

function heroRoots(root) {
  const matches =
    root instanceof HTMLElement && root.matches("[data-home-hero-media]")
      ? [root]
      : [];
  return [
    ...matches,
    ...(root.querySelectorAll?.("[data-home-hero-media]") ?? []),
  ];
}

function bindHeroVideo(hero) {
  if (!(hero instanceof HTMLElement) || boundHeroVideos.has(hero)) return;
  const video = hero.querySelector("[data-home-hero-video]");
  const control = hero.querySelector("[data-home-hero-control]");
  const playIcon = control?.querySelector("[data-home-hero-play-icon]");
  const pauseIcon = control?.querySelector("[data-home-hero-pause-icon]");
  if (
    !(video instanceof HTMLVideoElement) ||
    !(control instanceof HTMLButtonElement)
  ) {
    return;
  }
  boundHeroVideos.add(hero);

  const updateControl = (playing) => {
    const action = playing ? "暂停" : "播放";
    control.setAttribute("aria-label", `${action}首页主视觉视频`);
    control.title = `${action}首页主视觉视频`;
    playIcon?.toggleAttribute("hidden", playing);
    pauseIcon?.toggleAttribute("hidden", !playing);
  };

  const showPoster = () => {
    delete hero.dataset.videoStarted;
    updateControl(false);
  };

  const attemptPlay = () => {
    control.disabled = false;
    try {
      const pending = video.play();
      pending?.catch?.(() => {
        if (video.paused) showPoster();
      });
    } catch {
      showPoster();
    }
  };

  video.addEventListener("playing", () => {
    hero.dataset.videoStarted = "true";
    updateControl(true);
  });
  video.addEventListener("pause", () => updateControl(false));
  video.addEventListener("error", () => {
    video.pause();
    showPoster();
    control.disabled = true;
    control.setAttribute("aria-label", "首页主视觉视频暂时无法播放");
    control.title = "首页主视觉视频暂时无法播放";
  });
  control.addEventListener("click", () => {
    if (video.paused) attemptPlay();
    else video.pause();
  });

  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const applyMotionPreference = () => {
    if (motion.matches) {
      video.removeAttribute("autoplay");
      video.pause();
      showPoster();
    } else {
      attemptPlay();
    }
  };
  motion.addEventListener?.("change", applyMotionPreference);
  applyMotionPreference();
}

export function initializeHomeHeroMedia(root = document) {
  heroRoots(root).forEach(bindHeroVideo);
}
