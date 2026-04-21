import { useNavigate } from "react-router-dom";
import * as Icons from "lucide-react";
import EMPLOYEE_TEMPLATES from "../../data/employeeTemplates";

export default function TemplateGallery() {
  const navigate = useNavigate();

  return (
    <div className="mt-10">
      <h2 className="mb-4 text-lg font-semibold text-text-primary">
        Hire from Pool
      </h2>
      <div className="flex gap-4 overflow-x-auto pb-2">
        {EMPLOYEE_TEMPLATES.map((tmpl) => {
          const IconComp = Icons[tmpl.avatar] || Icons.Bot;
          return (
            <button
              key={tmpl.id}
              onClick={() => navigate(`/new?template=${tmpl.id}`)}
              className="flex w-56 shrink-0 flex-col gap-2 rounded-xl border border-border/40 bg-surface p-4 text-left transition-all hover:border-accent-teal/40 hover:bg-surface-hover"
            >
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-teal/10">
                <IconComp size={18} className="text-accent-teal" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary">
                {tmpl.name}
              </h3>
              <p className="line-clamp-2 text-xs text-text-muted">
                {tmpl.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
