-- liquibase formatted sql

--changeset cshah:001 Create orders table
-- This table is intentionally missing some things to test DQ validation
CREATE TABLE PLAYGROUND_DB.SILVER.ORDERS (
    ORDER_ID     NUMBER(38,0),
    CUSTOMER_ID  NUMBER(38,0),
    STATUS       VARCHAR(20),
    ORDER_AMOUNT NUMBER(18,2),
    ORDER_DATE   TIMESTAMP_NTZ
);

--changeset cshah:002 Create customers table
CREATE TABLE PLAYGROUND_DB.SILVER.CUSTOMERS (
    CUSTOMER_ID  NUMBER(38,0) NOT NULL,
    EMAIL        VARCHAR(255) NOT NULL,
    FIRST_NAME   VARCHAR(100),
    LAST_NAME    VARCHAR(100),
    CREATED_AT   TIMESTAMP_NTZ NOT NULL
) COMMENT = 'Customer master table';
