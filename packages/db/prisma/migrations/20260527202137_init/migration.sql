-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "Portal" AS ENUM ('MERCADOLIBRE');

-- CreateEnum
CREATE TYPE "OperationType" AS ENUM ('SALE', 'RENT', 'TEMP_RENT');

-- CreateEnum
CREATE TYPE "PropertyType" AS ENUM ('APT', 'HOUSE', 'PH', 'LOCAL', 'TERRENO', 'OTRO');

-- CreateEnum
CREATE TYPE "Currency" AS ENUM ('ARS', 'USD');

-- CreateEnum
CREATE TYPE "ScrapeJobStatus" AS ENUM ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED');

-- CreateTable
CREATE TABLE "properties" (
    "id" UUID NOT NULL,
    "portal" "Portal" NOT NULL,
    "portal_id" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "operation_type" "OperationType" NOT NULL,
    "property_type" "PropertyType" NOT NULL,
    "price_amount" DECIMAL(14,2) NOT NULL,
    "price_currency" "Currency" NOT NULL,
    "price_usd_normalized" DECIMAL(14,2),
    "expenses_amount" DECIMAL(14,2),
    "expenses_currency" "Currency",
    "bedrooms" INTEGER,
    "bathrooms" INTEGER,
    "total_sqm" DECIMAL(10,2),
    "covered_sqm" DECIMAL(10,2),
    "address_full" TEXT,
    "neighborhood" TEXT,
    "city" TEXT,
    "province" TEXT,
    "lat" DECIMAL(9,6),
    "lng" DECIMAL(9,6),
    "photos" JSONB NOT NULL DEFAULT '[]',
    "description" TEXT,
    "amenities" JSONB NOT NULL DEFAULT '{}',
    "agency_name" TEXT,
    "agency_phone" TEXT,
    "agency_email" TEXT,
    "agency_url" TEXT,
    "zone_slug" TEXT,
    "first_seen_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_seen_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_updated_at" TIMESTAMPTZ NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "properties_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "scrape_jobs" (
    "id" UUID NOT NULL,
    "portal" "Portal" NOT NULL,
    "params" JSONB NOT NULL,
    "status" "ScrapeJobStatus" NOT NULL DEFAULT 'PENDING',
    "started_at" TIMESTAMPTZ,
    "completed_at" TIMESTAMPTZ,
    "items_found" INTEGER NOT NULL DEFAULT 0,
    "items_created" INTEGER NOT NULL DEFAULT 0,
    "items_updated" INTEGER NOT NULL DEFAULT 0,
    "error_log" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "scrape_jobs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "usd_rates" (
    "id" UUID NOT NULL,
    "source" TEXT NOT NULL,
    "rate" DECIMAL(10,2) NOT NULL,
    "recorded_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "usd_rates_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "properties_operation_type_property_type_neighborhood_idx" ON "properties"("operation_type", "property_type", "neighborhood");

-- CreateIndex
CREATE INDEX "properties_zone_slug_operation_type_price_usd_normalized_idx" ON "properties"("zone_slug", "operation_type", "price_usd_normalized");

-- CreateIndex
CREATE INDEX "properties_last_seen_at_idx" ON "properties"("last_seen_at");

-- CreateIndex
CREATE INDEX "properties_is_active_idx" ON "properties"("is_active");

-- CreateIndex
CREATE UNIQUE INDEX "properties_portal_portal_id_key" ON "properties"("portal", "portal_id");

-- CreateIndex
CREATE INDEX "scrape_jobs_portal_status_idx" ON "scrape_jobs"("portal", "status");

-- CreateIndex
CREATE INDEX "scrape_jobs_created_at_idx" ON "scrape_jobs"("created_at");

-- CreateIndex
CREATE INDEX "usd_rates_recorded_at_idx" ON "usd_rates"("recorded_at");

-- CreateIndex
CREATE INDEX "usd_rates_source_recorded_at_idx" ON "usd_rates"("source", "recorded_at");

