<template>
  <main class="auth-page">
    <section class="auth-story" aria-label="产品介绍">
      <div class="brand brand--light">
        <span class="brand__mark" aria-hidden="true">知</span>
        <span>知序</span>
      </div>
      <div class="auth-story__content">
        <p class="eyebrow eyebrow--light">ENTERPRISE KNOWLEDGE</p>
        <h1>让每个答案，<br />都有据可查。</h1>
        <p class="auth-story__lead">
          检索企业文档，由 DeepSeek 基于授权证据回答，并保留可追溯引用。
        </p>
        <div class="story-flow" aria-label="问答过程">
          <span>权限验证</span><i aria-hidden="true"></i><span>混合检索</span
          ><i aria-hidden="true"></i><span>引用回答</span>
        </div>
      </div>
      <p class="auth-story__foot">本地开发环境 · 密钥不会发送到浏览器</p>
    </section>

    <section class="auth-form-wrap">
      <div class="auth-form-card">
        <slot />
      </div>
    </section>
  </main>
</template>
