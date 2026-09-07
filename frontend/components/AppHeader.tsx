import Link from "next/link";

import { BrandLink } from "@/components/BrandLink";
import { DEMO_MODE } from "@/lib/demo-mode";

type HeaderSection = "advice" | "programs" | "profile";

export function AppHeader({ active }: { active: HeaderSection }) {
  return (
    <header className="site-header">
      <BrandLink />
      <nav className="process-nav" aria-label="主导航">
        <Link className={active === "advice" ? "is-active" : undefined} aria-current={active === "advice" ? "page" : undefined} href="/advice">
          选校建议
        </Link>
        <Link className={active === "programs" ? "is-active" : undefined} aria-current={active === "programs" ? "page" : undefined} href="/programs">
          项目数据库
        </Link>
        <Link className={active === "profile" ? "is-active" : undefined} aria-current={active === "profile" ? "page" : undefined} href="/profile">
          申请档案
        </Link>
      </nav>
      <span className="dataset-chip"><i aria-hidden="true" /> {DEMO_MODE ? "公开演示 · 固定示例" : "20 项公开 Beta"}</span>
    </header>
  );
}
