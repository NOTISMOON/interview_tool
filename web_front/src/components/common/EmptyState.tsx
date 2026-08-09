interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  actionText?: string;
  onAction?: () => void;
}

const EmptyState = ({ icon = '📭', title, description, actionText, onAction }: EmptyStateProps) => {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <span className="text-5xl mb-4">{icon}</span>
      <h3 className="text-base font-semibold text-[#1e1b4b] mb-2">{title}</h3>
      {description && (
        <p className="text-sm text-[#6b7280] text-center mb-6 max-w-[280px]">{description}</p>
      )}
      {actionText && onAction && (
        <button onClick={onAction} className="gradient-btn text-sm">
          {actionText}
        </button>
      )}
    </div>
  );
};

export default EmptyState;