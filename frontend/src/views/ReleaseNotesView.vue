<template>
  <div class="release-page">
    <nav class="release-nav">
      <RouterLink class="release-brand" :to="{ name: 'Home' }" aria-label="PageAndNode home">
        <img src="../assets/logo/PageAndNode_mark.png" alt="" aria-hidden="true" />
        <span>PAGE</span><span class="brand-accent">AND</span><span>NODE</span>
      </RouterLink>
      <div class="release-nav-actions">
        <LanguageSwitcher />
        <RouterLink class="back-link" :to="{ name: 'Home' }">
          ← {{ pageCopy.backHome }}
        </RouterLink>
      </div>
    </nav>

    <main class="release-main">
      <header class="release-hero">
        <div class="release-kicker"><span>■</span> {{ pageCopy.label }}</div>
        <h1>{{ pageCopy.title }}</h1>
        <p>{{ pageCopy.intro }}</p>
      </header>

      <div class="release-layout">
        <aside class="release-index" :aria-label="pageCopy.label">
          <div class="release-index-label">{{ localizedReleases[0]?.timelineLabel }}</div>
          <a
            v-for="release in localizedReleases"
            :key="release.id"
            :href="'#' + release.id"
          >
            <time :datetime="release.date">{{ release.dateLabel }}</time>
            <span>{{ release.title }}</span>
          </a>
        </aside>

        <div class="release-feed">
          <article
            v-for="release in localizedReleases"
            :id="release.id"
            :key="release.id"
            class="release-article"
          >
            <header class="release-article-header">
              <div class="release-meta">
                <time :datetime="release.date">{{ release.dateLabel }}</time>
                <span>{{ release.badge }}</span>
              </div>
              <h2>{{ release.title }}</h2>
              <p>{{ release.intro }}</p>
            </header>

            <section class="release-section comparison-section">
              <h3>{{ release.comparisonLead }}</h3>
              <div class="comparison-scroll">
                <table>
                  <thead>
                    <tr>
                      <th v-for="heading in release.comparisonHeaders" :key="heading || 'dimension'">
                        {{ heading }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in release.comparisonRows" :key="row[0]">
                      <th scope="row">{{ row[0] }}</th>
                      <td>{{ row[1] }}</td>
                      <td>{{ row[2] }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section class="release-section walkthrough-section">
              <h3>{{ release.walkthroughHeading }}</h3>
              <ol>
                <li v-for="(item, index) in release.walkthrough" :key="item">
                  <span>{{ String(index + 1).padStart(2, '0') }}</span>
                  <p>{{ item }}</p>
                </li>
              </ol>
            </section>

            <section class="release-section conclusions-section">
              <h3>{{ release.conclusionsHeading }}</h3>
              <ul>
                <li v-for="item in release.conclusions" :key="item">{{ item }}</li>
              </ul>
            </section>

            <aside class="important-detail">
              <strong>{{ release.importantLabel }}</strong>
              <p>{{ release.importantDetail }}</p>
            </aside>

            <section class="release-section validation-section">
              <h3>{{ release.validationHeading }}</h3>
              <ul>
                <li v-for="item in release.validation" :key="item">{{ item }}</li>
              </ul>
            </section>
          </article>
        </div>
      </div>
    </main>

    <footer class="release-footer">
      <span>PAGEANDNODE</span>
      <RouterLink :to="{ name: 'Home' }">← {{ pageCopy.backHome }}</RouterLink>
    </footer>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import { releaseNotes, releasePageCopy } from '../releaseNotes.js'

const { locale } = useI18n()

const language = computed(() => (
  String(locale.value).toLowerCase().startsWith('zh') ? 'zh' : 'en'
))

const localizedReleases = computed(() => releaseNotes.map(release => ({
  id: release.id,
  date: release.date,
  ...release[language.value]
})))

const pageCopy = computed(() => ({
  ...releasePageCopy[language.value],
  backHome: localizedReleases.value[0]?.backHome || 'Back'
}))
</script>

<style scoped>
.release-page {
  --black: #000;
  --white: #fff;
  --orange: #ff4500;
  --soft: #f6f6f3;
  --line: #deded8;
  --muted: #666;
  --mono: 'JetBrains Mono', monospace;
  --sans: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  min-height: 100vh;
  background: var(--white);
  color: var(--black);
  font-family: var(--sans);
}

.release-nav {
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 10px 40px;
  background: var(--black);
  color: var(--white);
}

.release-brand {
  display: inline-flex;
  align-items: center;
  gap: 0.22rem;
  color: var(--white);
  font-family: var(--mono);
  font-size: 0.92rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-decoration: none;
}

.release-brand img {
  width: 42px;
  height: 34px;
  margin-right: 9px;
  background: var(--white);
  object-fit: contain;
}

.brand-accent {
  color: var(--orange);
  font-style: italic;
  font-weight: 300;
}

.release-nav-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-link {
  color: var(--white);
  font-family: var(--mono);
  font-size: 0.78rem;
  text-decoration: none;
}

.back-link:hover {
  color: var(--orange);
}

.release-nav :deep(.switcher-trigger) {
  color: var(--white);
  border-color: #555;
}

.release-nav :deep(.switcher-trigger:hover) {
  border-color: var(--orange);
}

.release-main {
  width: min(1320px, calc(100% - 80px));
  margin: 0 auto;
  padding: 80px 0 96px;
}

.release-hero {
  max-width: 970px;
  padding-bottom: 64px;
}

.release-kicker,
.release-index-label {
  color: #8a8a83;
  font-family: var(--mono);
  font-size: 0.76rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.release-kicker {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 26px;
}

.release-kicker span {
  color: var(--orange);
}

.release-hero h1 {
  max-width: 880px;
  margin: 0;
  font-size: clamp(3.1rem, 7vw, 6.8rem);
  font-weight: 520;
  letter-spacing: -0.065em;
  line-height: 0.95;
}

.release-hero > p {
  max-width: 720px;
  margin: 34px 0 0;
  color: var(--muted);
  font-size: 1.08rem;
  line-height: 1.75;
}

.release-layout {
  display: grid;
  grid-template-columns: minmax(210px, 0.3fr) minmax(0, 1fr);
  gap: 64px;
  align-items: start;
  border-top: 1px solid var(--black);
  padding-top: 28px;
}

.release-index {
  position: sticky;
  top: 24px;
}

.release-index-label {
  margin-bottom: 18px;
}

.release-index a {
  display: block;
  padding: 18px 0;
  border-top: 1px solid var(--line);
  color: var(--black);
  text-decoration: none;
}

.release-index a:last-child {
  border-bottom: 1px solid var(--line);
}

.release-index a:hover span {
  color: var(--orange);
}

.release-index time {
  display: block;
  margin-bottom: 8px;
  color: var(--orange);
  font-family: var(--mono);
  font-size: 0.7rem;
  font-weight: 700;
}

.release-index span {
  display: block;
  font-size: 0.88rem;
  font-weight: 560;
  line-height: 1.45;
}

.release-article {
  scroll-margin-top: 24px;
}

.release-article + .release-article {
  margin-top: 96px;
  border-top: 1px solid var(--black);
  padding-top: 72px;
}

.release-article-header {
  padding: 4px 0 54px;
}

.release-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 26px;
  font-family: var(--mono);
  font-size: 0.7rem;
  font-weight: 700;
}

.release-meta time {
  color: var(--orange);
}

.release-meta span {
  padding: 5px 8px;
  background: var(--orange);
  color: var(--white);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.release-article-header h2 {
  max-width: 880px;
  margin: 0;
  font-size: clamp(2.25rem, 5vw, 4.8rem);
  font-weight: 540;
  letter-spacing: -0.055em;
  line-height: 1;
}

.release-article-header p {
  max-width: 820px;
  margin: 28px 0 0;
  color: var(--muted);
  font-size: 1.03rem;
  line-height: 1.75;
}

.release-section {
  padding: 50px 0;
  border-top: 1px solid var(--line);
}

.release-section h3 {
  margin: 0 0 26px;
  font-size: clamp(1.55rem, 3vw, 2.45rem);
  font-weight: 560;
  letter-spacing: -0.04em;
}

.comparison-scroll {
  overflow-x: auto;
  border: 1px solid var(--black);
}

table {
  width: 100%;
  min-width: 720px;
  border-collapse: collapse;
}

th,
td {
  padding: 18px 20px;
  border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
  font-size: 0.86rem;
  line-height: 1.55;
}

tr:last-child th,
tr:last-child td {
  border-bottom: 0;
}

th:last-child,
td:last-child {
  border-right: 0;
}

thead th {
  background: var(--black);
  color: var(--white);
  font-size: 0.77rem;
  font-weight: 650;
}

tbody th {
  width: 22%;
  background: var(--soft);
  font-family: var(--mono);
  font-size: 0.72rem;
  font-weight: 650;
}

.walkthrough-section ol {
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--black);
  list-style: none;
}

.walkthrough-section li {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 20px;
  padding: 22px 0;
  border-bottom: 1px solid var(--line);
}

.walkthrough-section li > span {
  padding-top: 3px;
  color: var(--orange);
  font-family: var(--mono);
  font-size: 0.72rem;
  font-weight: 700;
}

.walkthrough-section p {
  margin: 0;
  font-size: 0.96rem;
  line-height: 1.75;
}

.conclusions-section ul,
.validation-section ul {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  margin: 0;
  padding: 1px;
  background: var(--line);
  list-style: none;
}

.conclusions-section li,
.validation-section li {
  position: relative;
  min-height: 132px;
  padding: 24px 26px 24px 48px;
  background: var(--white);
  font-size: 0.9rem;
  line-height: 1.65;
}

.conclusions-section li::before,
.validation-section li::before {
  content: "■";
  position: absolute;
  top: 27px;
  left: 24px;
  color: var(--orange);
  font-size: 0.55rem;
}

.important-detail {
  margin: 18px 0 50px;
  padding: 30px 32px;
  border-left: 5px solid var(--orange);
  background: var(--black);
  color: var(--white);
}

.important-detail strong {
  display: block;
  margin-bottom: 12px;
  color: var(--orange);
  font-family: var(--mono);
  font-size: 0.78rem;
}

.important-detail p {
  margin: 0;
  font-size: 1rem;
  line-height: 1.75;
}

.release-footer {
  min-height: 88px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 20px 40px;
  border-top: 1px solid var(--line);
  font-family: var(--mono);
  font-size: 0.72rem;
  font-weight: 700;
}

.release-footer a {
  color: var(--black);
  text-decoration: none;
}

.release-footer a:hover {
  color: var(--orange);
}

@media (max-width: 900px) {
  .release-main {
    width: min(100% - 48px, 1320px);
    padding-top: 60px;
  }

  .release-layout {
    grid-template-columns: 1fr;
    gap: 48px;
  }

  .release-index {
    position: static;
  }

  .release-index a {
    display: grid;
    grid-template-columns: 150px minmax(0, 1fr);
    gap: 18px;
  }
}

@media (max-width: 640px) {
  .release-nav {
    align-items: flex-start;
    flex-direction: column;
    padding: 12px 16px;
  }

  .release-nav-actions {
    width: 100%;
    justify-content: space-between;
  }

  .release-main {
    width: min(100% - 32px, 1320px);
    padding: 44px 0 64px;
  }

  .release-hero {
    padding-bottom: 44px;
  }

  .release-hero h1 {
    font-size: clamp(2.75rem, 14vw, 4.4rem);
  }

  .release-layout {
    gap: 38px;
  }

  .release-index a {
    grid-template-columns: 1fr;
    gap: 5px;
  }

  .release-article-header {
    padding-bottom: 42px;
  }

  .release-section {
    padding: 42px 0;
  }

  .walkthrough-section li {
    grid-template-columns: 34px minmax(0, 1fr);
    gap: 10px;
  }

  .conclusions-section ul,
  .validation-section ul {
    grid-template-columns: 1fr;
  }

  .conclusions-section li,
  .validation-section li {
    min-height: 0;
  }

  .important-detail {
    padding: 26px 24px;
  }

  .release-footer {
    align-items: flex-start;
    flex-direction: column;
    padding: 24px 16px;
  }
}
</style>
