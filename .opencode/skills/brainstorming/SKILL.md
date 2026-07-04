---
name: brainstorming
description: "Refina ideias usando método socrático. Agent faz perguntas para clarificar escopo."
---

<!--
  TÜRKÇE AÇIKLAMA
  ───────────────
  Bu skill, bir fikir veya problemi Sokratik yöntemle rafine eder. Agent sana
  cevap vermez — sorular sorar. Bu sorular aracılığıyla fikrin netleşir, varsayımlar
  sorgulanır, kapsam belirlenir ve gerçek ihtiyaç ortaya çıkar. "Ne yapalım?"
  sorusunu "Tam olarak ne yapmamız gerekiyor ve neden?" sorusuna dönüştürür.

  NE ZAMAN: Yeni bir özellik veya proje fikri gündeme geldiğinde, gereksinimler
            belirsiz olduğunda, ekip arasında farklı anlayışlar olduğunda.
  ÇIKTI:    Scope doc — netleşmiş problem, kapsam, kısıtlar, başarı kriterleri.
-->

---
name: brainstorming
description: >
  Socratic design refinement skill. Rather than jumping to solutions, this skill
  asks targeted questions to clarify the problem, challenge assumptions, define
  scope, and surface the real need. Turns "what should we build?" into a
  crisp, agreed-upon problem statement with success criteria.
---

# Brainstorming Skill — Socratic Design Refinement

## Felsefe

İyi çözümler iyi sorulardan gelir. Bu skill bir cevap üretmez — doğru soruları sormak için bir çerçeve sunar. Bir fikrin %80'i ilk ifade edilişinde eksiktir. Bu eksikliği kodu yazarken değil, düşünürken bulmak gerekir.

> "If I had an hour to solve a problem, I'd spend 55 minutes thinking about the problem and 5 minutes thinking about solutions." — Einstein

---

## Süreç

### Aşama 1: Problemi Dinle

Kullanıcı veya ekip fikri ifade eder. **Hemen çözüm önerme.** Önce şu soruları sor:

#### 🎯 Problem Netliği
- Bu özelliği/sistemi neden yapıyoruz? Hangi acıyı çözüyor?
- Bu olmadan ne oluyor? Şu an insanlar bu ihtiyacı nasıl karşılıyor?
- Kim için yapıyoruz? Bu kişilerin bugünkü günlük rutini nasıl?

#### 📏 Kapsam Sınırları
- Bu projenin kesinlikle kapsam **içinde** olduğu şeyler neler?
- Kesinlikle kapsam **dışında** olduğu şeyler neler?
- "Sonra ekleriz" dediklerimiz neler? (bunları şimdi tanımla, sonra tartışma)

#### ⚡ Kısıtlar
- Zaman kısıtı var mı? Sabit bir deadline var mı?
- Teknik kısıt var mı? (mevcut stack, bütçe, ekip kapasitesi)
- Düzenleyici veya yasal kısıt var mı?

#### ✅ Başarı Kriterleri
- Bu projenin başarılı olduğunu nasıl anlayacağız?
- Hangi metrik veya gözlem "bitti" dedirtir?
- 6 ay sonra bu kararı doğru mu yanlış mı bulduk — bunu ne belirler?

---

### Aşama 2: Varsayımları Zorla

Her fikrin altında açıklanmamış varsayımlar yatar. Bunları yüzeye çıkar:

```
"Kullanıcılar bu özelliği kullanmak isteyecek"
→ Bunu nasıl biliyoruz? Test ettik mi?

"Bu backend değişikliği basit olacak"
→ Bunu kim söyledi? Mevcut kodu bilen biri mi değerlendirdi?

"Önce X, sonra Y"
→ Neden bu sıra? Y olmadan X işe yarar mı?

"Mobil kullanıcılar önemli değil"
→ Mevcut analytics'e baktık mı? Bu bir karar mı, bir varsayım mı?
```

Her varsayımı şu şekilde sınıflandır:
- **Doğrulanmış:** Kanıtı var, güvenle devam
- **Makul:** Mantıklı ama test edilmemiş — riski not et
- **Tehlikeli:** Kanıtsız, yüksek etkili — önce doğrula

---

### Aşama 3: Alternatifleri Değerlendir

En az 3 yaklaşım üret ve karşılaştır:

| Yaklaşım | Artılar | Eksiler | Risk | Çaba |
|----------|---------|---------|------|------|
| Seçenek A | ... | ... | Düşük | 2 gün |
| Seçenek B | ... | ... | Orta | 1 hafta |
| Seçenek C | ... | ... | Yüksek | 3 hafta |

**"Hiç yapmama" seçeneğini her zaman tabloya ekle.** Bu seçeneğin maliyeti nedir?

---

### Aşama 4: Minimum Değerli Slice'ı Bul

Tam projeyi bir anda yapmak yerine:
- Değerin %80'ini veren %20'lik kısım nedir?
- Kullanıcıya en hızlı değer katan ilk slice ne?
- İlk iterasyonda kesinlikle olmaması gereken şeyler neler?

```
MVP = [özellik A, özellik B]
İterasyon 2 = [özellik C, özellik D]
Gelecek = [özellik E] — gerekirse
```

---

### Aşama 5: Scope Doc Yaz

Tüm soruları yanıtlandıktan sonra `.agent/SCOPE-<slug>.md` dosyasına yaz:

```markdown
# Scope: <proje adı>
**Tarih:** <YYYY-MM-DD>
**Karar Verenler:** <isimler>

## Problem
<Tek paragraf — ne acısını çözüyoruz, kimin için>

## Kapsam İçi
- <madde>

## Kapsam Dışı
- <madde>

## Başarı Kriterleri
1. <ölçülebilir kriter>
2. <ölçülebilir kriter>

## Doğrulanmamış Varsayımlar
- <varsayım> → <nasıl doğrulanacak>

## Seçilen Yaklaşım
<Seçenek X seçildi çünkü...>

## İlk Slice (MVP)
<Ne yapılacak, ne yapılmayacak>

## Sonraki Adım
→ `writing-plans` skill'i ile implementasyon planı oluştur
```

---

## Kurallar

- **Çözüme atlamak yasak.** Scope doc tamamlanmadan `writing-plans` başlamaz.
- **"Bence şöyle yapalım" demek yasak.** Bu skill soru sorar, cevap vermez.
- **Her varsayımı kayıt altına al.** Doğrulanmamış varsayım = gizli risk.
- **Scope doc kısa olmalı.** 1 sayfa yeterli. Daha uzunsa kapsam çok büyük.
- **İlk iterasyona "sonra ekleriz" girmez.** Girdiyse kesmek için argüman yok.
