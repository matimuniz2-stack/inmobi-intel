-- AlterTable
ALTER TABLE "properties" ADD COLUMN "title" TEXT;

-- CreateTable
CREATE TABLE "price_history" (
    "id" UUID NOT NULL,
    "property_id" UUID NOT NULL,
    "price_amount" DECIMAL(14,2) NOT NULL,
    "price_currency" "Currency" NOT NULL,
    "price_usd_normalized" DECIMAL(14,2),
    "observed_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "price_history_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "opportunities" (
    "id" UUID NOT NULL,
    "property_id" UUID NOT NULL,
    "score" INTEGER NOT NULL,
    "reasons" TEXT[],
    "signals" JSONB NOT NULL DEFAULT '{}',
    "price_usd_at_score" DECIMAL(14,2),
    "computed_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "opportunities_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "price_history_property_id_observed_at_idx" ON "price_history"("property_id", "observed_at");

-- CreateIndex
CREATE UNIQUE INDEX "opportunities_property_id_key" ON "opportunities"("property_id");

-- CreateIndex
CREATE INDEX "opportunities_score_idx" ON "opportunities"("score");

-- CreateIndex
CREATE INDEX "opportunities_computed_at_idx" ON "opportunities"("computed_at");

-- AddForeignKey
ALTER TABLE "price_history" ADD CONSTRAINT "price_history_property_id_fkey" FOREIGN KEY ("property_id") REFERENCES "properties"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "opportunities" ADD CONSTRAINT "opportunities_property_id_fkey" FOREIGN KEY ("property_id") REFERENCES "properties"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Backfill (data): sembrar un punto base de precio por cada propiedad que aún no
-- tenga historial, usando su precio actual fechado en first_seen_at. Así la señal
-- "baja reciente" tiene una referencia desde el día uno en vez de esperar un ciclo
-- completo de scrape. Idempotente vía NOT EXISTS.
INSERT INTO "price_history" ("id", "property_id", "price_amount", "price_currency", "price_usd_normalized", "observed_at")
SELECT gen_random_uuid(), p."id", p."price_amount", p."price_currency", p."price_usd_normalized", p."first_seen_at"
FROM "properties" p
WHERE NOT EXISTS (SELECT 1 FROM "price_history" ph WHERE ph."property_id" = p."id");
