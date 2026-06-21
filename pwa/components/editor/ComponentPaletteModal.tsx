// pwa/components/editor/ComponentPaletteModal.tsx

import type React from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { ICONS } from "../../constants";
import { useStrategyEditorStore, PRO_BLOCKS } from "../../stores/strategyEditorStore";
import { useAuth } from "../../contexts/AuthContext";
import { hasProPlanAccess } from "../../types";
import { api } from "../../services/api";
import {
	type ComponentType,
	type ConditionBlock,
	TOP_LEVEL_MANAGEMENT_BLOCK_TYPES,
} from "../../types/strategyEditor";
import { PALETTE_CONFIG } from "../../constants/blockConfig";

interface ComponentPaletteModalProps {
	isOpen: boolean;
	onClose: () => void;
	targetSection: "filters" | "entryConditions" | "positionManagement";
	parentId: string | null;
}

// Function to determine relevant block groups
const getPrimaryGroupKeys = (
	section: "filters" | "entryConditions" | "positionManagement",
): string[] => {
	switch (section) {
		case "filters":
			return ["filters", "foundations", "indicators", "logic"];
		case "entryConditions":
			return ["filters", "foundations", "indicators", "logic"];
		case "positionManagement":
			return ["management"];
		default:
			return [];
	}
};

const ComponentPaletteModal: React.FC<ComponentPaletteModalProps> = ({
	isOpen,
	onClose,
	targetSection,
	parentId,
}) => {
	const { t } = useTranslation("pwa-common");
	const { user } = useAuth();
	const isAdmin = user?.role === "admin";
	const hasProAccess = hasProPlanAccess(user?.plan) || isAdmin;

	const {
		addCondition,
		addManagementBlock,
		addConditionToManagementBlock,
		addCompositeCondition,
	} = useStrategyEditorStore();
	const [isExpanded, setIsExpanded] = useState(false);

	const { data: restrictions } = useQuery({
		queryKey: ["blockRestrictions"],
		queryFn: () => api.getBlockRestrictions(),
		staleTime: 1000 * 60 * 15, // 15 mins stale time
	});

	const proBlocks = restrictions?.proOnly || PRO_BLOCKS;

	useEffect(() => {
		if (isOpen) {
			const timer = setTimeout(() => {
				setIsExpanded(false);
			}, 0);
			return () => clearTimeout(timer);
		}
	}, [isOpen]);

	const handleAddComponent = (type: ComponentType) => {
		if (
			[
				"tape_condition",
				"order_book_zone_condition",
				"level_proximity_condition",
			].includes(type)
		) {
			if (targetSection === "filters" || targetSection === "entryConditions") {
				addCompositeCondition(
					targetSection,
					type as NonNullable<ConditionBlock["compositeType"]>,
				);
			}
		} else if (targetSection === "positionManagement") {
			if (parentId && !parentId.includes("root")) {
				addConditionToManagementBlock(parentId, type);
			} else if (
				TOP_LEVEL_MANAGEMENT_BLOCK_TYPES.includes(
					type as (typeof TOP_LEVEL_MANAGEMENT_BLOCK_TYPES)[number],
				)
			) {
				addManagementBlock(type);
			}
		} else {
			addCondition(targetSection, type, parentId);
		}
		onClose();
	};

	const renderGroup = (group: (typeof PALETTE_CONFIG)[0]) => {
		const standardItems = group.items.filter((item) => !proBlocks.includes(item.type));
		const proItems = group.items.filter((item) => proBlocks.includes(item.type));

		const handleItemClick = (item: (typeof group.items)[0], isProItem: boolean) => {
			if (isProItem && !hasProAccess) {
				alert(t("editor.proBlockLockedAlert", "This block requires a PRO plan subscription. Please upgrade to unlock it."));
				return;
			}
			handleAddComponent(item.type);
		};

		return (
			<div className="mb-6" key={group.groupKey}>
				<h2 className="text-base font-semibold text-[hsl(var(--foreground))] mb-3">
					{t(group.groupTitleKey)}
				</h2>

				{standardItems.length > 0 && (
					<div className="mb-4">
						{proItems.length > 0 && (
							<div className="text-xs text-[hsl(var(--muted-foreground))] mb-2 uppercase tracking-wider font-semibold">
								{t("editor.standardBlocks", "Standard Blocks")}
							</div>
						)}
						<div className="grid grid-cols-3 gap-3">
							{standardItems.map((item) => {
								const IconComponent = item.icon;
								return (
									<button
										key={item.type}
										onClick={() => handleItemClick(item, false)}
										className="bg-[hsl(var(--card))] rounded-xl p-3 flex flex-col items-center justify-center gap-2 aspect-square text-center transition-all hover:shadow-md hover:border-[hsl(var(--primary))] border border-transparent active:scale-95"
									>
										<div className="w-10 h-10 rounded-full bg-[hsl(var(--secondary))] flex items-center justify-center">
											<IconComponent className="w-5 h-5 text-[hsl(var(--primary))]" />
										</div>
										<div className="text-xs font-medium text-[hsl(var(--card-foreground))] leading-tight">
											{t(item.titleKey)}
										</div>
									</button>
								);
							})}
						</div>
					</div>
				)}

				{proItems.length > 0 && (
					<div>
						<div className="text-xs text-[hsl(var(--muted-foreground))] mb-2 uppercase tracking-wider font-semibold flex items-center gap-1.5">
							<span>⚡</span>
							<span>{t("editor.proBlocks", "PRO Blocks")}</span>
						</div>
						<div className="grid grid-cols-3 gap-3">
							{proItems.map((item) => {
								const IconComponent = item.icon;
								const isLocked = !hasProAccess;
								return (
									<button
										key={item.type}
										onClick={() => handleItemClick(item, true)}
										className={`relative bg-[hsl(var(--card))] rounded-xl p-3 flex flex-col items-center justify-center gap-2 aspect-square text-center transition-all border border-transparent ${
											isLocked ? "opacity-75" : "hover:shadow-md hover:border-[hsl(var(--primary))] active:scale-95"
										}`}
									>
										<div className="w-10 h-10 rounded-full bg-[hsl(var(--secondary))] flex items-center justify-center relative">
											<IconComponent className="w-5 h-5 text-[hsl(var(--primary))]" />
											{isLocked && (
												<div className="absolute inset-0 bg-black/60 rounded-full flex items-center justify-center">
													<Lock className="w-3.5 h-3.5 text-white" />
												</div>
											)}
										</div>
										<div className="text-xs font-medium text-[hsl(var(--card-foreground))] leading-tight">
											{t(item.titleKey)}
										</div>
										<div className="absolute top-1.5 right-1.5 px-1 py-0.2 bg-[hsl(var(--primary))] text-[8px] font-bold text-white rounded uppercase flex items-center gap-0.5 shadow-sm">
											<span>PRO</span>
										</div>
									</button>
								);
							})}
						</div>
					</div>
				)}
			</div>
		);
	};

	const primaryGroupKeys =
		targetSection === "positionManagement" &&
		parentId &&
		!parentId.includes("root")
			? ["filters", "foundations", "indicators", "logic"]
			: getPrimaryGroupKeys(targetSection);
	const primaryGroups = PALETTE_CONFIG.filter((g) =>
		primaryGroupKeys.includes(g.groupKey),
	);
	const secondaryGroups = PALETTE_CONFIG.filter(
		(g) => !primaryGroupKeys.includes(g.groupKey),
	);

	return (
		<div
			className={`fixed inset-0 bg-[hsl(var(--background))] z-50 flex flex-col transition-transform duration-300 ease-out ${isOpen ? "translate-y-0" : "translate-y-full"}`}
		>
			<header className="sticky top-0 bg-[hsl(var(--background))] p-4 shadow-sm flex items-center gap-4 z-10 border-b border-[hsl(var(--border))]">
				<button
					className="w-10 h-10 rounded-full flex items-center justify-center transition hover:bg-[hsl(var(--secondary))]"
					onClick={onClose}
				>
					<ICONS.Close className="w-6 h-6 text-[hsl(var(--foreground))]" />
				</button>
				<h1 className="text-xl font-normal flex-1 text-[hsl(var(--foreground))]">
					{t("modal.addBlock")}
				</h1>
			</header>

			<main className="flex-1 overflow-y-auto p-4">
				{primaryGroups.map(renderGroup)}

				{!isExpanded && secondaryGroups.length > 0 && (
					<div className="my-6">
						<button
							onClick={() => setIsExpanded(true)}
							className="w-full py-3 rounded-lg border-none text-sm font-medium bg-[hsl(var(--secondary))] text-[hsl(var(--secondary-foreground))] transition hover:opacity-90"
						>
							{t("editor.showAllBlocks")}
						</button>
					</div>
				)}

				{isExpanded && secondaryGroups.map(renderGroup)}
			</main>
		</div>
	);
};

export default ComponentPaletteModal;
