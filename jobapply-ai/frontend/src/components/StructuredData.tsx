export default function StructuredData() {
  const site = process.env.NEXT_PUBLIC_SITE_URL || "https://yourdomain.com";
  const graph = [
    { "@type": "Organization", "@id": `${site}/#organization`, name: "JobApply AI", url: site },
    { "@type": "WebSite", "@id": `${site}/#website`, name: "JobApply AI", url: site, publisher: { "@id": `${site}/#organization` } },
    { "@type": "SoftwareApplication", name: "JobApply AI", applicationCategory: "BusinessApplication", operatingSystem: "Web", description: "CV parsing, profile auto-fill, job matching, and application preparation." },
    { "@type": "FAQPage", mainEntity: [
      { "@type": "Question", name: "Can JobApply AI parse PDF and DOCX CVs?", acceptedAnswer: { "@type": "Answer", text: "Yes. JobApply AI extracts structured profile information from PDF and DOCX files and supports OCR fallback for scanned documents." } },
      { "@type": "Question", name: "Will parsed CV data overwrite my profile?", acceptedAnswer: { "@type": "Answer", text: "No. Parsed data fills empty profile fields. Existing information remains under your control." } },
      { "@type": "Question", name: "Are applications sent automatically?", acceptedAnswer: { "@type": "Answer", text: "No. You review and explicitly approve application content before sending." } },
    ] },
    { "@type": "BreadcrumbList", itemListElement: [{ "@type": "ListItem", position: 1, name: "Home", item: site }] },
  ];
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify({ "@context": "https://schema.org", "@graph": graph }) }} />;
}
