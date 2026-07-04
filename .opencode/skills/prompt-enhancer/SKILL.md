---
name: prompt-enhancer
description: "Transforma requisições vagas em prompts claros e acionáveis."
---

<!--
  TÜRKÇE AÇIKLAMA
  ───────────────
  Bu skill, belirsiz veya eksik bir kullanıcı isteğini alır ve onu daha net,
  daha spesifik, daha uygulanabilir bir prompt'a dönüştürür. Agent'ın yanlış
  anlayarak iş yapmasını önler. "Şunu düzelt" gibi muğlak bir istek,
  "hangi koşulda ne bekleniyor, başarı kriteri ne" formatına çevrilir.

  NE ZAMAN: İstek belirsizse, kapsam netleşmemişse, birden fazla yorum mümkünse.
            Diğer skilllerden önce çalıştırılır — girdi kalitesini artırır.
  ÇIKTI:    Geliştirilmiş prompt metni — doğrudan brainstorming veya writing-plans'a gider.
-->

---
name: prompt-enhancer
description: >
  Takes a vague or incomplete user request and transforms it into a precise,
  actionable prompt. Identifies missing dimensions (what, why, who, success criteria,
  constraints) and either asks targeted questions or fills gaps with explicit assumptions.
  Runs before other skills to improve input quality.
---

# Prompt Enhancer Skill

## Felsefe

Yanlış soruya doğru cevap vermek, doğru soruya yanlış cevap vermekten daha kötüdür.

Bir isteğin kalitesi, çıktısının kalitesini belirler. Bu skill, agent'ın "galiba bunu kastetti" modunda çalışmasını engeller. Belirsizliği yüzeye çıkarır ve karar noktalarını netleştirir.

---

## Ne Zaman Tetiklenir?

Şu sinyallerden biri varsa bu skill devreye girer:

- İstek tek cümle ve detaysız: *"Login'i düzelt"*, *"Performansı artır"*, *"Daha iyi görünsün"*
- İstek birden fazla şekilde yorumlanabilir: *"Kullanıcı flow'unu iyileştir"*
- Hedef kitle veya bağlam yok: *"Bir dashboard ekle"*
- Başarı kriteri belirsiz: *"Hızlandır"*, *"Temizle"*, *"Optimize et"*
- Kapsam sınırı yok: *"Auth sistemini yenile"*

---

## Süreç

### Adım 1: İstek Türünü Tespit Et

İlk olarak ne tür bir istek olduğunu belirle:

| Tür | Örnek | Eksik Boyutlar |
|-----|-------|----------------|
| **Bug fix** | "Login çalışmıyor" | Hangi koşulda? Hata mesajı? Her zaman mı? |
| **Yeni özellik** | "Profil sayfası ekle" | Kim kullanacak? İçerik ne? Tasarım referansı? |
| **Refactor** | "Kodu temizle" | Hangi dosya/modül? Temizden kasıt ne? |
| **Performans** | "Hızlandır" | Hangi sayfa/endpoint? Hedef süre? Mevcut süre? |
| **Tasarım** | "Daha güzel yap" | Referans var mı? Hangi element? Hangi bağlam? |
| **Altyapı** | "Deploy otomatikleştir" | Hangi ortam? Mevcut pipeline? Tetikleyici ne? |

---

### Adım 2: Eksik Boyutları Bul

Her istek için şu 6 boyutu kontrol et. Eksik olanları işaretle:

```
[ ] WHAT   — Tam olarak ne değişecek/eklenecek?
[ ] WHY    — Neden gerekli? Hangi problemi çözüyor?
[ ] WHO    — Kim kullanacak? Hangi kullanıcı/sistem?
[ ] WHEN   — Deadline var mı? Hangi sırayla?
[ ] HOW    — Kısıt var mı? (stack, platform, bütçe, mevcut API)
[ ] DONE   — Başarı kriteri ne? "Bitti" ne zaman söylenecek?
```

---

### Adım 3: Geliştirme Stratejisini Seç

**Strateji A — Sor** (1-2 kritik belirsizlik varsa):

Sadece en önemli soruları sor. Her soruya neden sorulduğunu belirt:

```
Sana 2 sorum var — bunlara göre farklı yaklaşım seçeceğim:

1. "Login çalışmıyor" derken — hangi koşulda?
   a) Her zaman mı?
   b) Belirli bir tarayıcıda mı?
   c) Belirli bir kullanıcıda mı?
   (Bu, bug'ın scope'unu belirliyor)

2. Mevcut hata mesajı veya log var mı?
   (Varsa paylaşırsan köken analizi çok daha hızlı olur)
```

**Strateji B — Varsay ve Göster** (3+ belirsizlik varsa, hızlı ilerleme öncelikli):

Makul varsayımlar yap, bunları açıkça listele ve enhanced prompt'u üret:

```
İstek: "Profil sayfası ekle"

Varsayımlar (onaylamanı bekliyorum):
- Kullanıcı: giriş yapmış kayıtlı kullanıcılar
- İçerik: isim, email, avatar, bio
- Tasarım: mevcut design system'e uygun
- Auth: JWT token ile korumalı route
- Kapsam: frontend + backend endpoint

Bu varsayımlardan farklı bir şey var mı? Yoksa bu scope ile başlayalım.
```

---

### Adım 4: Enhanced Prompt'u Üret

Her iki stratejide de son çıktı format aşağıdaki gibi olur:

```markdown
## Enhanced Prompt

**Asıl İstek:** <kullanıcının orijinal isteği>

**Netleştirilmiş Görev:**
<spesifik, tek yorumlu açıklama>

**Kapsam İçi:**
- <madde>
- <madde>

**Kapsam Dışı:**
- <madde> (kapsam dışı bırakma gerekçesi)

**Başarı Kriterleri:**
1. <ölçülebilir kriter>
2. <ölçülebilir kriter>

**Teknik Kısıtlar:**
- <stack, platform, bağımlılık>

**Açık Kalan Sorular:**
- <varsa — bunlar ilerleyen aşamada cevaplanacak>

**Önerilen Sonraki Skill:**
→ <brainstorming | writing-plans | test-driven-execution>
```

---

### Adım 5: Kullanıcıdan Onay Al

Enhanced prompt'u kullanıcıya göster:

```
Şu şekilde anladım — doğru mu?

[Enhanced Prompt içeriği]

Onaylıyorsan başlayabilirim. Değiştirmek istediğin bir şey var mı?
```

Onay gelmeden bir sonraki skill'e geçilmez.

---

## Örnekler

### Örnek 1: Bug Fix

**Kullanıcı:** *"Şifre sıfırlama çalışmıyor"*

**Tespit:**
- WHAT: şifre sıfırlama — ama hangi adımda?
- HOW: hata mesajı yok
- WHO: tüm kullanıcılar mı, belirli biri mi?

**Strateji A — Sor:**
```
"Şifre sıfırlama" akışının hangi adımında sorun var?
  a) Email gönderilmiyor mu?
  b) Link tıklanınca hata mı veriyor?
  c) Yeni şifre kaydedilmiyor mu?
```

---

### Örnek 2: Performans

**Kullanıcı:** *"Sayfa çok yavaş"*

**Tespit:** 6 boyutun 5'i eksik.

**Strateji B — Varsay ve Göster:**
```
Şu varsayımlarla devam edeyim:
- Hangi sayfa: /dashboard (en çok kullanılan)
- Mevcut durum: 4-5 saniye TTI (tahmin)
- Hedef: 2 saniye altı
- Platform: web (mobile değil)
- Kısıt: mevcut stack değişmiyor

Farklıysa söyle, yoksa Lighthouse profili çekerek başlayacağım.
```

---

## Kurallar

- **Her zaman onay al.** Enhanced prompt kullanıcı onayı olmadan uygulanmaz.
- **Maksimum 3 soru sor.** Daha fazlası kullanıcıyı yorar — en kritik 3'ü seç.
- **Varsayımları gizleme.** Her varsayım açıkça listelenir.
- **Kapsam dışını da yaz.** "Bunu yapmıyorum çünkü" = en değerli netlik.
- **Sonraki skill'i öner.** Enhanced prompt'tan sonra hangi skill çalışacak belirt.
