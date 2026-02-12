import { useState } from 'react';
import { PlusIcon, TrashIcon, PencilIcon } from '@heroicons/react/24/outline';
import { Button, Modal, ConfirmDialog } from '../../components/ui';
import {
  useBundles,
  useCreateBundle,
  useUpdateBundle,
  useDeleteBundle,
} from '../../hooks/useQuotes';
import { showSuccess, showError } from '../../utils/toast';
import type {
  ProductBundle,
  ProductBundleCreate,
  ProductBundleUpdate,
  ProductBundleItemCreate,
} from '../../types';

interface BundleFormProps {
  onSubmit: (data: ProductBundleCreate | ProductBundleUpdate) => void;
  onCancel: () => void;
  isLoading?: boolean;
  initialData?: ProductBundle;
}

function BundleForm({ onSubmit, onCancel, isLoading, initialData }: BundleFormProps) {
  const [name, setName] = useState(initialData?.name ?? '');
  const [description, setDescription] = useState(initialData?.description ?? '');
  const [isActive, setIsActive] = useState(initialData?.is_active ?? true);
  const [items, setItems] = useState<ProductBundleItemCreate[]>(
    initialData?.items?.map((item) => ({
      description: item.description,
      quantity: item.quantity,
      unit_price: item.unit_price,
      sort_order: item.sort_order,
    })) ?? [{ description: '', quantity: 1, unit_price: 0, sort_order: 0 }]
  );

  const addItem = () => {
    setItems((curr) => [...curr, { description: '', quantity: 1, unit_price: 0, sort_order: curr.length }]);
  };

  const removeItem = (index: number) => {
    setItems((curr) => curr.filter((_, i) => i !== index));
  };

  const updateItem = (index: number, field: keyof ProductBundleItemCreate, value: string | number) => {
    setItems((curr) =>
      curr.map((item, i) => (i === index ? { ...item, [field]: value } : item))
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      name,
      description: description || undefined,
      is_active: isActive,
      items: items.filter((item) => item.description.trim() !== ''),
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="bundle-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Name *
        </label>
        <input
          type="text"
          id="bundle-name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
          placeholder="Bundle name..."
        />
      </div>
      <div>
        <label htmlFor="bundle-desc" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Description
        </label>
        <input
          type="text"
          id="bundle-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
          placeholder="Optional description..."
        />
      </div>
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="bundle-active"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
        />
        <label htmlFor="bundle-active" className="text-sm text-gray-700 dark:text-gray-300">Active</label>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">Items</h4>
          <button
            type="button"
            onClick={addItem}
            className="inline-flex items-center text-sm text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
          >
            <PlusIcon className="h-4 w-4 mr-1" aria-hidden="true" />
            Add Item
          </button>
        </div>
        <div className="space-y-2">
          {items.map((item, index) => (
            <div key={index} className="flex gap-2 items-center">
              <div className="flex-1">
                <label htmlFor={`bundle-item-desc-${index}`} className="sr-only">Description</label>
                <input
                  type="text"
                  id={`bundle-item-desc-${index}`}
                  value={item.description}
                  onChange={(e) => updateItem(index, 'description', e.target.value)}
                  placeholder="Description..."
                  className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
                />
              </div>
              <div className="w-20">
                <label htmlFor={`bundle-item-qty-${index}`} className="sr-only">Quantity</label>
                <input
                  type="number"
                  id={`bundle-item-qty-${index}`}
                  value={item.quantity}
                  onChange={(e) => updateItem(index, 'quantity', parseFloat(e.target.value) || 0)}
                  min="0"
                  step="any"
                  placeholder="Qty"
                  className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
                />
              </div>
              <div className="w-28">
                <label htmlFor={`bundle-item-price-${index}`} className="sr-only">Price</label>
                <input
                  type="number"
                  id={`bundle-item-price-${index}`}
                  value={item.unit_price}
                  onChange={(e) => updateItem(index, 'unit_price', parseFloat(e.target.value) || 0)}
                  min="0"
                  step="any"
                  placeholder="Price"
                  className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
                />
              </div>
              <button
                type="button"
                onClick={() => removeItem(index)}
                className="p-1 text-gray-400 hover:text-red-600 dark:hover:text-red-400"
                aria-label={`Remove bundle item ${index + 1}`}
                disabled={items.length <= 1}
              >
                <TrashIcon className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={isLoading || !name.trim()}>
          {isLoading ? 'Saving...' : initialData ? 'Update Bundle' : 'Create Bundle'}
        </Button>
      </div>
    </form>
  );
}

export function BundleManager() {
  const { data: bundlesData, isLoading } = useBundles();
  const createMutation = useCreateBundle();
  const updateMutation = useUpdateBundle();
  const deleteMutation = useDeleteBundle();

  const bundles = bundlesData?.items ?? [];

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editBundle, setEditBundle] = useState<ProductBundle | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; bundle: ProductBundle | null }>({
    isOpen: false,
    bundle: null,
  });

  const handleCreate = async (data: ProductBundleCreate | ProductBundleUpdate) => {
    try {
      await createMutation.mutateAsync(data as ProductBundleCreate);
      setShowCreateForm(false);
      showSuccess('Bundle created');
    } catch {
      showError('Failed to create bundle');
    }
  };

  const handleUpdate = async (data: ProductBundleCreate | ProductBundleUpdate) => {
    if (!editBundle) return;
    try {
      await updateMutation.mutateAsync({ id: editBundle.id, data: data as ProductBundleUpdate });
      setEditBundle(null);
      showSuccess('Bundle updated');
    } catch {
      showError('Failed to update bundle');
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm.bundle) return;
    try {
      await deleteMutation.mutateAsync(deleteConfirm.bundle.id);
      setDeleteConfirm({ isOpen: false, bundle: null });
      showSuccess('Bundle deleted');
    } catch {
      showError('Failed to delete bundle');
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-transparent dark:border-gray-700">
      <div className="px-6 py-4 flex items-center justify-between border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100">Product Bundles</h2>
        <Button
          size="sm"
          leftIcon={<PlusIcon className="h-4 w-4" />}
          onClick={() => setShowCreateForm(true)}
        >
          New Bundle
        </Button>
      </div>

      {isLoading ? (
        <div className="px-6 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
          Loading bundles...
        </div>
      ) : bundles.length === 0 ? (
        <div className="px-6 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
          No bundles yet. Create one to get started.
        </div>
      ) : (
        <div className="divide-y divide-gray-200 dark:divide-gray-700">
          {bundles.map((bundle: ProductBundle) => (
            <div key={bundle.id} className="px-6 py-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">{bundle.name}</h3>
                  {bundle.description && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{bundle.description}</p>
                  )}
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    {bundle.items.length} item{bundle.items.length !== 1 ? 's' : ''}
                    {!bundle.is_active && (
                      <span className="ml-2 text-yellow-600 dark:text-yellow-400">Inactive</span>
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setEditBundle(bundle)}
                    className="p-1 text-gray-400 hover:text-primary-600 dark:hover:text-primary-400"
                    aria-label={`Edit ${bundle.name}`}
                  >
                    <PencilIcon className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteConfirm({ isOpen: true, bundle })}
                    className="p-1 text-gray-400 hover:text-red-600 dark:hover:text-red-400"
                    aria-label={`Delete ${bundle.name}`}
                  >
                    <TrashIcon className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        isOpen={showCreateForm}
        onClose={() => setShowCreateForm(false)}
        title="Create Bundle"
        size="md"
      >
        <BundleForm
          onSubmit={handleCreate}
          onCancel={() => setShowCreateForm(false)}
          isLoading={createMutation.isPending}
        />
      </Modal>

      <Modal
        isOpen={editBundle !== null}
        onClose={() => setEditBundle(null)}
        title="Edit Bundle"
        size="md"
      >
        {editBundle && (
          <BundleForm
            onSubmit={handleUpdate}
            onCancel={() => setEditBundle(null)}
            isLoading={updateMutation.isPending}
            initialData={editBundle}
          />
        )}
      </Modal>

      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={() => setDeleteConfirm({ isOpen: false, bundle: null })}
        onConfirm={handleDelete}
        title="Delete Bundle"
        message={`Are you sure you want to delete "${deleteConfirm.bundle?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
